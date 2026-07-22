"""Private screenshot intake and provider-neutral multimodal extraction for M0-4C."""

from __future__ import annotations

import asyncio
import base64
import json
import warnings
from collections.abc import AsyncIterable, Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from typing import Final

from PIL import Image, UnidentifiedImageError

from app.application.extraction_output import (
    build_repair_messages,
    canonicalize_extraction_result,
    parse_extraction_response,
)
from app.config import StorageProviderSettings
from app.domain.collections import (
    CandidateField,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    PlaceCandidate,
    Uncertainty,
)
from app.domain.time import require_aware_utc
from app.providers.storage import (
    PrivateFileMetadata,
    RetentionPolicy,
    StorageProvider,
    StorageProviderError,
)
from app.storage_policy import (
    STORAGE_SIGNATURE_PROBE_BYTES,
    content_signature_matches,
)
from nanobot_core.providers import Message, ModelProvider, ModelResponse, ProviderError

MAX_IMAGE_WIDTH: Final = 12_000
MAX_IMAGE_HEIGHT: Final = 12_000
MAX_IMAGE_PIXELS: Final = 40_000_000
ORIGINAL_SCREENSHOT_RETENTION_DAYS: Final = 30

_PIL_FORMAT_BY_CONTENT_TYPE: Final = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_RESULT_SCHEMA = json.dumps(
    ExtractionResult.model_json_schema(),
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
_SYSTEM_PROMPT = (
    "You extract structured collection candidates from one user-provided screenshot "
    "for Shiguang. OCR is evidence only; return no OCR transcript.\n"
    "Return exactly one JSON object matching this JSON Schema, without Markdown or "
    f"commentary:\n{_RESULT_SCHEMA}\n\n"
    "Rules:\n"
    "- Produce one separate candidate per distinct Place or user-supplied Event. Never "
    "merge multiple places.\n"
    "- A clear title may form a candidate. If only a shop name is visible, keep the "
    "title and explicitly mark every absent field missing or uncertain.\n"
    "- If the screenshot is blurred, unreadable, or insufficient, return "
    "insufficient_information. Never guess.\n"
    "- Screenshot prices are unconfirmed clues. Include PRICE uncertainty whenever a "
    "price is present.\n"
    "- city_hint, district, address, business district, landmark, and metro station are "
    "unconfirmed screenshot clues only. Mark every present one uncertain. Never emit a "
    "formal city code, POI, provider, coordinates, or confirmed location.\n"
    "- Do not turn business opening hours into Event start/end fields and do not invent "
    "a screenshot-only opening-hours field.\n"
    "- Do not use EXIF location or other hidden metadata as a confirmed place.\n"
    "- Do not include image bytes, Base64, OCR transcripts, prompts, provider fields, "
    "credentials, filenames, paths, or raw responses in the JSON.\n"
)
_USER_INSTRUCTION = (
    "Analyze the attached screenshot and return only the required structured result."
)
_LOCATION_FIELDS: Final = (
    CandidateField.CITY_HINT,
    CandidateField.DISTRICT,
    CandidateField.ADDRESS,
    CandidateField.BUSINESS_DISTRICT,
    CandidateField.LANDMARK,
    CandidateField.METRO_STATION,
)


class ImageRecognitionErrorCode(StrEnum):
    INVALID_REQUEST = "IMAGE_INVALID_REQUEST"
    CONTENT_TYPE_NOT_ALLOWED = "IMAGE_CONTENT_TYPE_NOT_ALLOWED"
    CONTENT_SIGNATURE_MISMATCH = "IMAGE_CONTENT_SIGNATURE_MISMATCH"
    FILE_EMPTY = "IMAGE_FILE_EMPTY"
    FILE_TOO_LARGE = "IMAGE_FILE_TOO_LARGE"
    CORRUPT_IMAGE = "IMAGE_CORRUPT"
    DIMENSIONS_EXCEEDED = "IMAGE_DIMENSIONS_EXCEEDED"
    PIXELS_EXCEEDED = "IMAGE_PIXELS_EXCEEDED"
    ANIMATED_IMAGE_NOT_ALLOWED = "IMAGE_ANIMATED_NOT_ALLOWED"
    PROCESSING_FAILED = "IMAGE_PROCESSING_FAILED"


_ERROR_SUMMARIES = {
    ImageRecognitionErrorCode.INVALID_REQUEST: "The screenshot request is invalid.",
    ImageRecognitionErrorCode.CONTENT_TYPE_NOT_ALLOWED: (
        "The screenshot type is not allowed."
    ),
    ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH: (
        "The screenshot content does not match its declared type."
    ),
    ImageRecognitionErrorCode.FILE_EMPTY: "The screenshot is empty.",
    ImageRecognitionErrorCode.FILE_TOO_LARGE: "The screenshot exceeds the size limit.",
    ImageRecognitionErrorCode.CORRUPT_IMAGE: "The screenshot is damaged or incomplete.",
    ImageRecognitionErrorCode.DIMENSIONS_EXCEEDED: (
        "The screenshot dimensions exceed the safety limit."
    ),
    ImageRecognitionErrorCode.PIXELS_EXCEEDED: (
        "The screenshot pixel count exceeds the safety limit."
    ),
    ImageRecognitionErrorCode.ANIMATED_IMAGE_NOT_ALLOWED: (
        "Animated screenshots are not supported."
    ),
    ImageRecognitionErrorCode.PROCESSING_FAILED: (
        "The screenshot could not be processed."
    ),
}


class ImageRecognitionError(Exception):
    """Fixed public-safe image failure without bytes, filename, or filesystem data."""

    def __init__(self, *, code: ImageRecognitionErrorCode) -> None:
        if not isinstance(code, ImageRecognitionErrorCode):
            raise TypeError("code must be an ImageRecognitionErrorCode")
        summary = _ERROR_SUMMARIES[code]
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = False

    def to_public_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "summary": self.summary,
            "retryable": self.retryable,
        }


class ImageRecognitionService:
    """Validate, store, and recognize one screenshot without a second result schema."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        storage: StorageProvider,
        storage_config: StorageProviderSettings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> None:
        if not isinstance(storage_config, StorageProviderSettings):
            raise TypeError("storage_config must be StorageProviderSettings")
        self._provider = provider
        self._storage = storage
        self._max_file_size_bytes = storage_config.max_file_size_bytes
        self._allowed_content_types = storage_config.allowed_content_types
        self._clock = clock
        self._response_observer = response_observer

    async def recognize(
        self,
        file: AsyncIterable[bytes],
        *,
        content_type: str,
        original_filename: str | None = None,
    ) -> tuple[PrivateFileMetadata, ExtractionResult]:
        """Return the existing file metadata and existing extraction result contracts."""

        image_bytes = await self._read_bounded(file)
        self._validate_image(image_bytes, content_type=content_type)
        expires_at = require_aware_utc(self._clock()) + timedelta(
            days=ORIGINAL_SCREENSHOT_RETENTION_DAYS
        )
        stored_file: PrivateFileMetadata | None = None
        unexpected_failure = False
        try:
            stored_file = await self._storage.put_private(
                _single_chunk(image_bytes),
                content_type=content_type,
                retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
                expires_at=expires_at,
                original_filename=original_filename,
            )
            result = await self._extract(image_bytes, content_type=content_type)
            return stored_file, result
        except asyncio.CancelledError:
            if stored_file is not None:
                await self._best_effort_delete(stored_file.file_key)
            raise
        except (ProviderError, StorageProviderError):
            if stored_file is not None:
                await self._best_effort_delete(stored_file.file_key)
            raise
        except ImageRecognitionError:
            if stored_file is not None:
                await self._best_effort_delete(stored_file.file_key)
            raise
        except Exception:
            unexpected_failure = True
        if unexpected_failure:
            if stored_file is not None:
                await self._best_effort_delete(stored_file.file_key)
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.PROCESSING_FAILED
            )
        raise AssertionError("unreachable screenshot recognition state")

    async def _extract(
        self,
        image_bytes: bytes,
        *,
        content_type: str,
    ) -> ExtractionResult:
        data_url = (
            f"data:{content_type};base64,"
            f"{base64.b64encode(image_bytes).decode('ascii')}"
        )
        initial_messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_INSTRUCTION},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                ],
            },
        ]
        first_response = await self._provider.chat(
            messages=initial_messages,
            tools=None,
        )
        self._observe(first_response)
        first_result, issues = parse_extraction_response(first_response)
        if first_result is not None:
            return _canonicalize_image_result(first_result)

        repaired_response = await self._provider.chat(
            messages=build_repair_messages(
                initial_messages,
                invalid_response=first_response,
                issues=issues,
            ),
            tools=None,
        )
        self._observe(repaired_response)
        repaired_result, _repaired_issues = parse_extraction_response(repaired_response)
        if repaired_result is not None:
            return _canonicalize_image_result(repaired_result)
        return ExtractionResult.model_invalid()

    async def _read_bounded(self, file: AsyncIterable[bytes]) -> bytes:
        if not hasattr(file, "__aiter__"):
            raise ImageRecognitionError(code=ImageRecognitionErrorCode.INVALID_REQUEST)
        payload = bytearray()
        invalid_stream = False
        try:
            async for chunk in file:
                if not isinstance(chunk, bytes):
                    raise ImageRecognitionError(
                        code=ImageRecognitionErrorCode.INVALID_REQUEST
                    )
                if len(payload) + len(chunk) > self._max_file_size_bytes:
                    raise ImageRecognitionError(
                        code=ImageRecognitionErrorCode.FILE_TOO_LARGE
                    )
                payload.extend(chunk)
        except asyncio.CancelledError:
            raise
        except ImageRecognitionError:
            raise
        except Exception:
            invalid_stream = True
        if invalid_stream:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.INVALID_REQUEST
            )
        if not payload:
            raise ImageRecognitionError(code=ImageRecognitionErrorCode.FILE_EMPTY)
        return bytes(payload)

    def _validate_image(self, payload: bytes, *, content_type: str) -> None:
        if (
            not isinstance(content_type, str)
            or content_type not in self._allowed_content_types
        ):
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CONTENT_TYPE_NOT_ALLOWED
            )
        prefix = payload[:STORAGE_SIGNATURE_PROBE_BYTES]
        if not content_signature_matches(content_type=content_type, prefix=prefix):
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH
            )

        corrupt_image = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(payload)) as image:
                    self._validate_open_image(image, content_type=content_type)
                    image.verify()
                with Image.open(BytesIO(payload)) as decoded:
                    self._validate_open_image(decoded, content_type=content_type)
                    decoded.load()
        except ImageRecognitionError:
            raise
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
        ):
            corrupt_image = True
        if corrupt_image:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CORRUPT_IMAGE
            )

    @staticmethod
    def _validate_open_image(image: Image.Image, *, content_type: str) -> None:
        if image.format != _PIL_FORMAT_BY_CONTENT_TYPE[content_type]:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH
            )
        width, height = image.size
        if width < 1 or height < 1:
            raise ImageRecognitionError(code=ImageRecognitionErrorCode.CORRUPT_IMAGE)
        if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.DIMENSIONS_EXCEEDED
            )
        if width * height > MAX_IMAGE_PIXELS:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.PIXELS_EXCEEDED
            )
        if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.ANIMATED_IMAGE_NOT_ALLOWED
            )

    def _observe(self, response: ModelResponse | None) -> None:
        if isinstance(response, ModelResponse) and self._response_observer is not None:
            self._response_observer(response)

    async def _best_effort_delete(self, file_key: str) -> None:
        try:
            await self._storage.delete(file_key)
        except (asyncio.CancelledError, StorageProviderError):
            return


async def _single_chunk(payload: bytes) -> AsyncIterable[bytes]:
    yield payload


def _canonicalize_image_result(result: ExtractionResult) -> ExtractionResult:
    if result.outcome is not ExtractionOutcome.CANDIDATES:
        return canonicalize_extraction_result(
            result,
            insufficient_recovery_suggestions=(
                "请重新上传更清晰的截图，或补充具体店名、活动名和位置线索。",
            ),
        )
    candidates = tuple(_mark_screenshot_uncertainties(item) for item in result.candidates)
    return ExtractionResult.with_candidates(candidates)


def _mark_screenshot_uncertainties(
    candidate: PlaceCandidate | EventCandidate,
) -> PlaceCandidate | EventCandidate:
    existing = {item.field: item for item in candidate.uncertainties}
    present_location_fields = {
        CandidateField.CITY_HINT: candidate.city_hint is not None,
        CandidateField.DISTRICT: candidate.district is not None,
        CandidateField.ADDRESS: candidate.address is not None,
        CandidateField.BUSINESS_DISTRICT: candidate.business_district is not None,
        CandidateField.LANDMARK: candidate.landmark is not None,
        CandidateField.METRO_STATION: candidate.metro_station is not None,
    }
    uncertainties = list(candidate.uncertainties)
    for field in _LOCATION_FIELDS:
        if present_location_fields[field] and field not in existing:
            uncertainties.append(
                Uncertainty(
                    field=field,
                    reason="截图位置线索尚未经过地图或用户确认。",
                )
            )
    if candidate.price_amount is not None and CandidateField.PRICE not in existing:
        uncertainties.append(
            Uncertainty(field=CandidateField.PRICE, reason="截图中的价格需要用户确认。")
        )

    payload = candidate.model_dump(mode="python")
    payload["uncertainties"] = tuple(uncertainties)
    if isinstance(candidate, PlaceCandidate):
        return PlaceCandidate.model_validate(payload)
    return EventCandidate.model_validate(payload)


__all__ = [
    "ImageRecognitionError",
    "ImageRecognitionErrorCode",
    "ImageRecognitionService",
    "MAX_IMAGE_HEIGHT",
    "MAX_IMAGE_PIXELS",
    "MAX_IMAGE_WIDTH",
    "ORIGINAL_SCREENSHOT_RETENTION_DAYS",
]
