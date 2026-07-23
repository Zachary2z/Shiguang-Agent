"""Private screenshot intake and provider-neutral multimodal extraction for M0-4C."""

from __future__ import annotations

import asyncio
import base64
import warnings
from collections.abc import AsyncIterable, Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from typing import Final

from PIL import Image, UnidentifiedImageError

from app.application.extraction_output import (
    EXTRACTION_SEMANTIC_RULES,
    build_repair_messages,
    canonicalize_extraction_result,
    extraction_response_format,
    extraction_result_schema_json,
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
from nanobot_core.providers import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderError,
    StructuredOutputMode,
)

MAX_IMAGE_WIDTH: Final = 12_000
MAX_IMAGE_HEIGHT: Final = 12_000
MAX_IMAGE_PIXELS: Final = 40_000_000
MIN_MODEL_IMAGE_DIMENSION: Final = 11
MAX_MODEL_IMAGE_ASPECT_RATIO: Final = 200
MAX_MODEL_IMAGE_PIXELS: Final = 4_000_000
MAX_MODEL_IMAGE_SIDE: Final = 4_096
MAX_MODEL_DATA_URL_CHARS: Final = 10_000_000
ORIGINAL_SCREENSHOT_RETENTION_DAYS: Final = 30
_INFERENCE_JPEG_QUALITIES: Final = (85, 70, 55)
_INFERENCE_RESIZE_ATTEMPTS: Final = 6

_PIL_FORMAT_BY_CONTENT_TYPE: Final = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_SYSTEM_PROMPT = (
    "You extract structured collection candidates from one user-provided screenshot "
    "for Shiguang. OCR is evidence only; return no OCR transcript.\n"
    "Return exactly one JSON object matching this JSON Schema, without Markdown or "
    f"commentary:\n{extraction_result_schema_json()}\n\n"
    "Rules:\n"
    f"{EXTRACTION_SEMANTIC_RULES}"
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
    MODEL_DIMENSIONS_UNSUPPORTED = "IMAGE_MODEL_DIMENSIONS_UNSUPPORTED"
    MODEL_ASPECT_RATIO_EXCEEDED = "IMAGE_MODEL_ASPECT_RATIO_EXCEEDED"
    MODEL_PAYLOAD_EXCEEDED = "IMAGE_MODEL_PAYLOAD_EXCEEDED"
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
    ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED: (
        "The screenshot dimensions are not supported for recognition."
    ),
    ImageRecognitionErrorCode.MODEL_ASPECT_RATIO_EXCEEDED: (
        "The screenshot aspect ratio is not supported for recognition."
    ),
    ImageRecognitionErrorCode.MODEL_PAYLOAD_EXCEEDED: (
        "The screenshot cannot be prepared within the recognition limit."
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
        structured_output_mode: StructuredOutputMode | None = None,
        response_observer: Callable[[ModelResponse], None] | None = None,
    ) -> None:
        if not isinstance(storage_config, StorageProviderSettings):
            raise TypeError("storage_config must be StorageProviderSettings")
        self._provider = provider
        self._storage = storage
        self._max_file_size_bytes = storage_config.max_file_size_bytes
        self._allowed_content_types = storage_config.allowed_content_types
        self._clock = clock
        self._response_format = extraction_response_format(structured_output_mode)
        self._response_observer = response_observer

    async def recognize(
        self,
        file: AsyncIterable[bytes],
        *,
        content_type: str,
        original_filename: str | None = None,
    ) -> tuple[PrivateFileMetadata, ExtractionResult]:
        """Return the existing file metadata and existing extraction result contracts."""

        self._validate_content_type(content_type)
        image_bytes = await self._read_bounded(file)
        preparation_error: ImageRecognitionError | None = None
        preparation_cancellation: asyncio.CancelledError | None = None
        unexpected_preparation_failure = False
        inference_bytes: bytes | None = None
        inference_content_type: str | None = None
        expires_at: datetime | None = None
        try:
            dimensions = self._validate_image(image_bytes, content_type=content_type)
            inference_bytes, inference_content_type = self._prepare_inference_image(
                image_bytes,
                content_type=content_type,
                dimensions=dimensions,
            )
            expires_at = require_aware_utc(self._clock()) + timedelta(
                days=ORIGINAL_SCREENSHOT_RETENTION_DAYS
            )
        except asyncio.CancelledError as error:
            preparation_cancellation = error
        except ImageRecognitionError as error:
            preparation_error = error
        except Exception:
            unexpected_preparation_failure = True

        if preparation_cancellation is not None:
            raise preparation_cancellation
        if preparation_error is not None:
            raise preparation_error
        if unexpected_preparation_failure:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.PROCESSING_FAILED
            )
        assert inference_bytes is not None
        assert inference_content_type is not None
        assert expires_at is not None
        stored_file: PrivateFileMetadata | None = None
        public_error: ProviderError | StorageProviderError | ImageRecognitionError | None = None
        cancellation: asyncio.CancelledError | None = None
        unexpected_failure = False
        try:
            stored_file = await self._storage.put_private(
                _single_chunk(image_bytes),
                content_type=content_type,
                retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
                expires_at=expires_at,
                original_filename=original_filename,
            )
            result = await self._extract(
                inference_bytes,
                content_type=inference_content_type,
            )
            return stored_file, result
        except asyncio.CancelledError as error:
            cancellation = error
        except (ProviderError, StorageProviderError, ImageRecognitionError) as error:
            public_error = error
        except Exception:
            unexpected_failure = True

        cleanup_failed = False
        if stored_file is not None:
            cleanup_failed = not await self._delete_current_file(stored_file.file_key)
        if cancellation is not None:
            raise cancellation
        if unexpected_failure or cleanup_failed:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.PROCESSING_FAILED
            )
        if public_error is not None:
            raise public_error
        raise AssertionError("unreachable screenshot recognition state")

    async def _extract(
        self,
        image_bytes: bytes,
        *,
        content_type: str,
    ) -> ExtractionResult:
        data_url = _build_model_data_url(image_bytes, content_type=content_type)
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
            response_format=self._response_format,
        )
        self._observe(first_response)
        first_result, issues = parse_extraction_response(first_response)
        if first_result is not None:
            return _canonicalize_image_result(first_result)

        repair_messages = build_repair_messages(
            initial_messages,
            invalid_response=first_response,
            issues=issues,
        )
        if repair_messages is None:
            return ExtractionResult.model_invalid()
        repaired_response = await self._provider.chat(
            messages=repair_messages,
            tools=None,
            response_format=self._response_format,
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

    def _validate_content_type(self, content_type: str) -> None:
        if not isinstance(content_type, str) or content_type not in self._allowed_content_types:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CONTENT_TYPE_NOT_ALLOWED
            )

    def _validate_image(self, payload: bytes, *, content_type: str) -> tuple[int, int]:
        prefix = payload[:STORAGE_SIGNATURE_PROBE_BYTES]
        if not content_signature_matches(content_type=content_type, prefix=prefix):
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH
            )

        corrupt_image = False
        dimensions: tuple[int, int] | None = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(payload)) as image:
                    self._validate_open_image(image, content_type=content_type)
                    dimensions = image.size
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
        assert dimensions is not None
        return dimensions

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
        if width < MIN_MODEL_IMAGE_DIMENSION or height < MIN_MODEL_IMAGE_DIMENSION:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED
            )
        if max(width, height) > min(width, height) * MAX_MODEL_IMAGE_ASPECT_RATIO:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.MODEL_ASPECT_RATIO_EXCEEDED
            )
        if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
            raise ImageRecognitionError(
                code=ImageRecognitionErrorCode.ANIMATED_IMAGE_NOT_ALLOWED
            )

    def _observe(self, response: ModelResponse | None) -> None:
        if isinstance(response, ModelResponse) and self._response_observer is not None:
            self._response_observer(response)

    def _prepare_inference_image(
        self,
        payload: bytes,
        *,
        content_type: str,
        dimensions: tuple[int, int],
    ) -> tuple[bytes, str]:
        width, height = dimensions
        if (
            width * height <= MAX_MODEL_IMAGE_PIXELS
            and max(width, height) <= MAX_MODEL_IMAGE_SIDE
            and _model_payload_fits(payload, content_type=content_type)
        ):
            return payload, content_type

        failed = False
        try:
            with Image.open(BytesIO(payload)) as source:
                source.load()
                inference = source.convert("RGB")
            inference = _resize_for_model(inference)
            for attempt in range(_INFERENCE_RESIZE_ATTEMPTS):
                for quality in _INFERENCE_JPEG_QUALITIES:
                    output = BytesIO()
                    inference.save(
                        output,
                        format="JPEG",
                        quality=quality,
                        optimize=False,
                        progressive=False,
                    )
                    encoded = output.getvalue()
                    if _model_dimensions_fit(inference.size) and _model_payload_fits(
                        encoded,
                        content_type="image/jpeg",
                    ):
                        return encoded, "image/jpeg"
                if attempt + 1 < _INFERENCE_RESIZE_ATTEMPTS:
                    next_size = (
                        max(MIN_MODEL_IMAGE_DIMENSION, int(inference.width * 0.75)),
                        max(MIN_MODEL_IMAGE_DIMENSION, int(inference.height * 0.75)),
                    )
                    inference = inference.resize(next_size, Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            failed = True
        if failed:
            raise ImageRecognitionError(code=ImageRecognitionErrorCode.PROCESSING_FAILED)
        raise ImageRecognitionError(code=ImageRecognitionErrorCode.MODEL_PAYLOAD_EXCEEDED)

    async def _delete_current_file(self, file_key: str) -> bool:
        unexpected_failure = False
        try:
            await self._storage.delete(file_key)
        except asyncio.CancelledError:
            raise
        except StorageProviderError:
            return True
        except Exception:
            unexpected_failure = True
        return not unexpected_failure


async def _single_chunk(payload: bytes) -> AsyncIterable[bytes]:
    yield payload


def _resize_for_model(image: Image.Image) -> Image.Image:
    scale = min(
        1.0,
        MAX_MODEL_IMAGE_SIDE / max(image.size),
        (MAX_MODEL_IMAGE_PIXELS / (image.width * image.height)) ** 0.5,
    )
    if scale >= 1.0:
        return image
    width = max(MIN_MODEL_IMAGE_DIMENSION, int(image.width * scale))
    height = max(MIN_MODEL_IMAGE_DIMENSION, int(image.height * scale))
    if width >= height:
        minimum_height = (
            width + MAX_MODEL_IMAGE_ASPECT_RATIO - 1
        ) // MAX_MODEL_IMAGE_ASPECT_RATIO
        height = max(height, minimum_height)
    else:
        minimum_width = (
            height + MAX_MODEL_IMAGE_ASPECT_RATIO - 1
        ) // MAX_MODEL_IMAGE_ASPECT_RATIO
        width = max(width, minimum_width)
    size = (
        width,
        height,
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _model_dimensions_fit(size: tuple[int, int]) -> bool:
    width, height = size
    return (
        width >= MIN_MODEL_IMAGE_DIMENSION
        and height >= MIN_MODEL_IMAGE_DIMENSION
        and max(width, height) <= MAX_MODEL_IMAGE_SIDE
        and width * height <= MAX_MODEL_IMAGE_PIXELS
        and max(width, height) <= min(width, height) * MAX_MODEL_IMAGE_ASPECT_RATIO
    )


def _base64_encoded_length(byte_size: int) -> int:
    return 4 * ((byte_size + 2) // 3)


def _model_payload_fits(payload: bytes, *, content_type: str) -> bool:
    prefix_length = len(f"data:{content_type};base64,")
    return prefix_length + _base64_encoded_length(len(payload)) < MAX_MODEL_DATA_URL_CHARS


def _build_model_data_url(payload: bytes, *, content_type: str) -> str:
    if not _model_payload_fits(payload, content_type=content_type):
        raise ImageRecognitionError(code=ImageRecognitionErrorCode.MODEL_PAYLOAD_EXCEEDED)
    encoded = base64.b64encode(payload).decode("ascii")
    assert len(encoded) == _base64_encoded_length(len(payload))
    data_url = f"data:{content_type};base64,{encoded}"
    assert len(data_url) < MAX_MODEL_DATA_URL_CHARS
    return data_url


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
    "MAX_MODEL_DATA_URL_CHARS",
    "MAX_MODEL_IMAGE_ASPECT_RATIO",
    "MAX_MODEL_IMAGE_PIXELS",
    "MAX_MODEL_IMAGE_SIDE",
    "MIN_MODEL_IMAGE_DIMENSION",
    "ORIGINAL_SCREENSHOT_RETENTION_DAYS",
]
