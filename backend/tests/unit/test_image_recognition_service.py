"""Offline M0-4C screenshot validation, lifecycle, and extraction tests."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import struct
import zlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

import app.application.image_recognition as image_recognition_module
from app.application.extraction_output import EXTRACTION_SEMANTIC_RULES
from app.application.image_recognition import (
    MAX_IMAGE_WIDTH,
    MAX_MODEL_DATA_URL_CHARS,
    MAX_MODEL_IMAGE_ASPECT_RATIO,
    MAX_MODEL_IMAGE_PIXELS,
    MAX_MODEL_IMAGE_SIDE,
    MIN_MODEL_IMAGE_DIMENSION,
    ImageRecognitionError,
    ImageRecognitionErrorCode,
    ImageRecognitionService,
)
from app.config import StorageProviderSettings
from app.domain.collections import (
    CandidateField,
    EventCandidate,
    ExtractionOutcome,
    ExtractionResult,
    PlaceCandidate,
)
from app.infrastructure.storage import LocalPrivateStorageProvider
from app.providers.storage import (
    RetentionPolicy,
    StorageProviderError,
    StorageProviderErrorCode,
)
from nanobot_core.providers import (
    Message,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    StructuredOutputMode,
    ToolCall,
    ToolDefinition,
)
from tests.core.fakes import FakeProvider, fake_response
from tests.fixtures.images import (
    BLURRED_PNG_SCREENSHOT,
    JPEG_SCREENSHOT,
    PNG_SCREENSHOT,
    WEBP_SCREENSHOT,
)

FIXED_NOW = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
FAKE_FILENAME = "private-name-secret.png"
COMMON_OPTIONAL_FIELDS = (
    CandidateField.CITY_HINT,
    CandidateField.DISTRICT,
    CandidateField.ADDRESS,
    CandidateField.BUSINESS_DISTRICT,
    CandidateField.LANDMARK,
    CandidateField.METRO_STATION,
    CandidateField.PRICE,
    CandidateField.TAGS,
)


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def _failing_stream(private_detail: str) -> AsyncIterator[bytes]:
    yield PNG_SCREENSHOT[:20]
    raise RuntimeError(private_detail)


def _storage_config(
    root: Path,
    *,
    max_file_size_bytes: int = 10_000_000,
) -> StorageProviderSettings:
    return StorageProviderSettings(
        private_root=root,
        max_file_size_bytes=max_file_size_bytes,
        allowed_content_types=frozenset(
            {"image/jpeg", "image/png", "image/webp"}
        ),
    )


def _service(
    tmp_path: Path,
    provider: FakeProvider,
    *,
    max_file_size_bytes: int = 10_000_000,
    structured_output_mode: StructuredOutputMode | None = None,
) -> tuple[ImageRecognitionService, LocalPrivateStorageProvider, Path]:
    root = tmp_path / "private-images"
    config = _storage_config(root, max_file_size_bytes=max_file_size_bytes)
    storage = LocalPrivateStorageProvider(
        config=config,
        clock=lambda: FIXED_NOW,
    )
    return (
        ImageRecognitionService(
            provider=provider,
            storage=storage,
            storage_config=config,
            clock=lambda: FIXED_NOW,
            structured_output_mode=structured_output_mode,
        ),
        storage,
        root,
    )


def _place(
    title: str = "海边咖啡",
    *,
    city_hint: str | None = None,
    district: str | None = None,
    address: str | None = None,
    business_district: str | None = None,
    landmark: str | None = None,
    metro_station: str | None = None,
    price: Decimal | None = None,
) -> PlaceCandidate:
    present = {
        CandidateField.CITY_HINT: city_hint is not None,
        CandidateField.DISTRICT: district is not None,
        CandidateField.ADDRESS: address is not None,
        CandidateField.BUSINESS_DISTRICT: business_district is not None,
        CandidateField.LANDMARK: landmark is not None,
        CandidateField.METRO_STATION: metro_station is not None,
        CandidateField.PRICE: price is not None,
    }
    missing = tuple(
        field
        for field in COMMON_OPTIONAL_FIELDS
        if not present.get(field, False)
    )
    return PlaceCandidate(
        title=title,
        city_hint=city_hint,
        district=district,
        address=address,
        business_district=business_district,
        landmark=landmark,
        metro_station=metro_station,
        price_amount=price,
        price_currency="CNY" if price is not None else None,
        missing_fields=missing,
    )


def _event() -> EventCandidate:
    return EventCandidate(
        title="夏日艺术展",
        city_hint="深圳",
        district="福田区",
        event_start_at=datetime(2026, 8, 1, 2, 0, tzinfo=UTC),
        event_end_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        missing_fields=(
            CandidateField.ADDRESS,
            CandidateField.BUSINESS_DISTRICT,
            CandidateField.LANDMARK,
            CandidateField.METRO_STATION,
            CandidateField.EVENT_START_DATE,
            CandidateField.EVENT_END_DATE,
            CandidateField.PRICE,
            CandidateField.TAGS,
        ),
    )


def _response_for(*candidates: PlaceCandidate | EventCandidate) -> ModelResponse:
    payload = ExtractionResult.with_candidates(tuple(candidates)).model_dump_json()
    return fake_response(content=payload)


def _invalid_candidate_response(title: str = "海边咖啡") -> ModelResponse:
    payload = json.loads(
        ExtractionResult.with_candidates((_place(title),)).model_dump_json()
    )
    payload["candidates"][0]["missing_fields"].append("city_hint")
    return fake_response(content=json.dumps(payload, ensure_ascii=False))


class _EvidenceCheckingImageProvider(FakeProvider):
    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        if self.calls:
            rendered = json.dumps(messages, ensure_ascii=False)
            assert "海边咖啡" in rendered
            assert '"role": "assistant"' in rendered
            assert "data:image/" not in rendered
            assert ";base64," not in rendered
            assert FAKE_FILENAME not in rendered
            assert "/private-images/" not in rendered
        return await super().chat(
            messages=messages,
            tools=tools,
            response_format=response_format,
        )


def _recognized_image_price_without_currency_response(amount: Decimal) -> ModelResponse:
    payload = json.loads(
        ExtractionResult.with_candidates((_place(price=amount),)).model_dump_json()
    )
    payload["candidates"][0].pop("price_currency")
    return fake_response(content=json.dumps(payload, ensure_ascii=False))


def _assert_no_storage_residue(root: Path) -> None:
    for child in ("objects", "metadata", ".tmp", ".reservations"):
        assert list((root / child).iterdir()) == []


def _png_with_dimensions(width: int, height: int) -> bytes:
    payload = bytearray(PNG_SCREENSHOT)
    payload[16:20] = struct.pack(">I", width)
    payload[20:24] = struct.pack(">I", height)
    payload[29:33] = struct.pack(">I", zlib.crc32(payload[12:29]) & 0xFFFFFFFF)
    return bytes(payload)


def _encoded_solid_image(
    size: tuple[int, int],
    *,
    image_format: str = "PNG",
) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(42, 124, 180)).save(output, format=image_format)
    return output.getvalue()


def _incompressible_png() -> bytes:
    size = (1_700, 1_700)
    pixels = random.Random(20260722).randbytes(size[0] * size[1] * 3)
    output = BytesIO()
    Image.frombytes("RGB", size, pixels).save(output, format="PNG", compress_level=0)
    return output.getvalue()


@pytest.mark.parametrize(
    ("payload", "content_type"),
    [
        (JPEG_SCREENSHOT, "image/jpeg"),
        (PNG_SCREENSHOT, "image/png"),
        (WEBP_SCREENSHOT, "image/webp"),
    ],
)
@pytest.mark.asyncio
async def test_supported_images_are_private_and_use_one_model_call(
    tmp_path: Path,
    payload: bytes,
    content_type: str,
) -> None:
    provider = FakeProvider([_response_for(_place())])
    service, storage, root = _service(tmp_path, provider)

    metadata, result = await service.recognize(
        _stream(payload),
        content_type=content_type,
        original_filename=FAKE_FILENAME,
    )

    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert result.candidates[0].title == "海边咖啡"
    assert metadata.content_type == content_type
    assert metadata.retention_policy is RetentionPolicy.ORIGINAL_SCREENSHOT
    assert metadata.expires_at == FIXED_NOW + timedelta(days=30)
    assert metadata.byte_size == len(payload)
    assert len(provider.calls) == 1
    assert provider.calls[0].tools is None
    user_content = provider.calls[0].messages[1]["content"]
    assert isinstance(user_content, list)
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith(
        f"data:{content_type};base64,"
    )
    access = await storage.get_private_access(metadata.file_key)
    assert access.file == metadata
    public_values = f"{metadata!r}{access!r}{result!r}"
    assert FAKE_FILENAME not in public_values
    assert "file://" not in public_values
    assert str(root) not in public_values


@pytest.mark.asyncio
async def test_large_incompressible_png_uses_bounded_inference_copy_only(
    tmp_path: Path,
) -> None:
    payload = _incompressible_png()
    assert 8_600_000 < len(payload) < 8_800_000
    assert len(base64.b64encode(payload)) > MAX_MODEL_DATA_URL_CHARS
    provider = FakeProvider([_response_for(_place())])
    service, storage, root = _service(tmp_path, provider)

    metadata, result = await service.recognize(
        _stream(payload),
        content_type="image/png",
        original_filename=FAKE_FILENAME,
    )

    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert metadata.byte_size == len(payload)
    assert metadata.content_type == "image/png"
    assert metadata.retention_policy is RetentionPolicy.ORIGINAL_SCREENSHOT
    assert metadata.expires_at == FIXED_NOW + timedelta(days=30)
    assert (await storage.get_private_access(metadata.file_key)).file == metadata
    assert [path.name for path in (root / "objects").iterdir()] == [metadata.file_key]
    user_content = provider.calls[0].messages[1]["content"]
    assert isinstance(user_content, list)
    data_url = user_content[1]["image_url"]["url"]
    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(data_url) < MAX_MODEL_DATA_URL_CHARS
    assert base64_marker(payload) not in data_url
    inference_payload = base64.b64decode(data_url.partition(",")[2], validate=True)
    with Image.open(BytesIO(inference_payload)) as inference:
        width, height = inference.size
        assert width >= MIN_MODEL_IMAGE_DIMENSION
        assert height >= MIN_MODEL_IMAGE_DIMENSION
        assert max(width, height) <= MAX_MODEL_IMAGE_SIDE
        assert width * height <= MAX_MODEL_IMAGE_PIXELS
        assert max(width, height) <= min(width, height) * MAX_MODEL_IMAGE_ASPECT_RATIO
    assert len(provider.calls) == 1


def test_model_data_url_exact_threshold_and_one_raw_byte_over() -> None:
    content_type = "image/jpeg"
    prefix_length = len(f"data:{content_type};base64,")
    accepted_quads = (MAX_MODEL_DATA_URL_CHARS - prefix_length - 1) // 4
    accepted_payload = b"x" * (accepted_quads * 3)

    data_url = image_recognition_module._build_model_data_url(
        accepted_payload,
        content_type=content_type,
    )

    assert len(data_url) < MAX_MODEL_DATA_URL_CHARS
    assert len(data_url) + 1 == MAX_MODEL_DATA_URL_CHARS
    with pytest.raises(ImageRecognitionError) as exc_info:
        image_recognition_module._build_model_data_url(
            accepted_payload + b"x",
            content_type=content_type,
        )
    assert exc_info.value.code is ImageRecognitionErrorCode.MODEL_PAYLOAD_EXCEEDED


@pytest.mark.asyncio
async def test_known_oversize_model_payload_never_reaches_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_type = "image/jpeg"
    prefix_length = len(f"data:{content_type};base64,")
    accepted_quads = (MAX_MODEL_DATA_URL_CHARS - prefix_length - 1) // 4
    oversize = b"x" * (accepted_quads * 3 + 1)
    provider = FakeProvider([])
    service, _storage, root = _service(tmp_path, provider)
    monkeypatch.setattr(
        service,
        "_prepare_inference_image",
        lambda *_args, **_kwargs: (oversize, content_type),
    )

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value.code is ImageRecognitionErrorCode.MODEL_PAYLOAD_EXCEEDED
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_clear_event_screenshot_uses_existing_event_candidate(tmp_path: Path) -> None:
    provider = FakeProvider([_response_for(_event())])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    candidate = result.candidates[0]
    assert isinstance(candidate, EventCandidate)
    assert candidate.title == "夏日艺术展"
    assert {item.field for item in candidate.uncertainties} >= {
        CandidateField.CITY_HINT,
        CandidateField.DISTRICT,
    }


@pytest.mark.asyncio
async def test_phone_status_bar_time_is_excluded_from_event_schedule_prompt(
    tmp_path: Path,
) -> None:
    provider = FakeProvider([_response_for(_place("状态栏下的地点"))])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    system_prompt = str(provider.calls[0].messages[0]["content"])
    assert "status-bar clocks and dates" in system_prompt
    candidate = result.candidates[0]
    assert isinstance(candidate, PlaceCandidate)
    assert "event_start_at" not in candidate.model_dump()
    assert "event_start_date" not in candidate.model_dump()


@pytest.mark.asyncio
async def test_shop_name_only_keeps_title_and_explicit_gaps(tmp_path: Path) -> None:
    provider = FakeProvider([_response_for(_place("M Stand"))])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    candidate = result.candidates[0]
    assert candidate.title == "M Stand"
    assert candidate.city_hint is None
    assert candidate.missing_fields == COMMON_OPTIONAL_FIELDS


@pytest.mark.asyncio
async def test_blurred_screenshot_returns_information_gap_without_guessing(
    tmp_path: Path,
) -> None:
    insufficient = ExtractionResult.insufficient(
        missing_fields=(CandidateField.TITLE, CandidateField.CITY_HINT),
        recovery_suggestions=("untrusted model suggestion",),
    )
    provider = FakeProvider([fake_response(content=insufficient.model_dump_json())])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(BLURRED_PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.INSUFFICIENT_INFORMATION
    assert result.candidates == ()
    assert result.recovery_suggestions == (
        "请重新上传更清晰的截图，或补充具体店名、活动名和位置线索。",
    )


@pytest.mark.asyncio
async def test_multiple_places_remain_separate(tmp_path: Path) -> None:
    provider = FakeProvider(
        [_response_for(_place("第一家店"), _place("第二家店"))]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert [candidate.title for candidate in result.candidates] == [
        "第一家店",
        "第二家店",
    ]


@pytest.mark.asyncio
async def test_price_and_all_location_clues_are_forced_uncertain(tmp_path: Path) -> None:
    model_candidate = _place(
        city_hint="深圳",
        district="南山区",
        address="海边路 1 号",
        business_district="海岸城",
        landmark="人才公园",
        metro_station="后海站",
        price=Decimal("55"),
    )
    provider = FakeProvider([_response_for(model_candidate)])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    candidate = result.candidates[0]
    assert {item.field for item in candidate.uncertainties} >= {
        CandidateField.CITY_HINT,
        CandidateField.DISTRICT,
        CandidateField.ADDRESS,
        CandidateField.BUSINESS_DISTRICT,
        CandidateField.LANDMARK,
        CandidateField.METRO_STATION,
        CandidateField.PRICE,
    }
    public = candidate.model_dump(mode="json")
    assert "city_code" not in public
    assert "poi_id" not in public
    assert "coordinates" not in public
    assert "opening_hours" not in public


@pytest.mark.asyncio
async def test_image_price_uses_shared_cny_default_and_prompt(tmp_path: Path) -> None:
    provider = FakeProvider(
        [_recognized_image_price_without_currency_response(Decimal("50"))]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    candidate = result.candidates[0]
    assert candidate.price_amount == Decimal("50")
    assert candidate.price_currency == "CNY"
    assert CandidateField.PRICE in {
        uncertainty.field for uncertainty in candidate.uncertainties
    }
    system_prompt = provider.calls[0].messages[0]["content"]
    assert "renminbi only" in system_prompt
    assert 'price_currency "CNY"' in system_prompt


@pytest.mark.parametrize(
    ("payload", "content_type", "expected"),
    [
        (b"", "image/png", ImageRecognitionErrorCode.FILE_EMPTY),
        (b"not-an-image", "image/png", ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH),
        (PNG_SCREENSHOT, "image/jpeg", ImageRecognitionErrorCode.CONTENT_SIGNATURE_MISMATCH),
        (
            PNG_SCREENSHOT,
            "application/octet-stream",
            ImageRecognitionErrorCode.CONTENT_TYPE_NOT_ALLOWED,
        ),
        (PNG_SCREENSHOT[:30], "image/png", ImageRecognitionErrorCode.CORRUPT_IMAGE),
        (
            _png_with_dimensions(MAX_IMAGE_WIDTH + 1, 1),
            "image/png",
            ImageRecognitionErrorCode.DIMENSIONS_EXCEEDED,
        ),
        (
            _png_with_dimensions(7_000, 7_000),
            "image/png",
            ImageRecognitionErrorCode.PIXELS_EXCEEDED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_unsafe_images_never_reach_storage_or_model(
    tmp_path: Path,
    payload: bytes,
    content_type: str,
    expected: ImageRecognitionErrorCode,
) -> None:
    provider = FakeProvider([])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(_stream(payload), content_type=content_type)

    assert exc_info.value.code is expected
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((10, 10), ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED),
        ((10, 11), ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED),
        ((11, 2_201), ImageRecognitionErrorCode.MODEL_ASPECT_RATIO_EXCEEDED),
    ],
)
@pytest.mark.asyncio
async def test_model_dimension_and_aspect_boundaries_are_rejected_before_storage(
    tmp_path: Path,
    size: tuple[int, int],
    expected: ImageRecognitionErrorCode,
) -> None:
    provider = FakeProvider([])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            _stream(_encoded_solid_image(size)),
            content_type="image/png",
        )

    assert exc_info.value.code is expected
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_exact_200_to_1_aspect_ratio_is_supported(tmp_path: Path) -> None:
    provider = FakeProvider([_response_for(_place())])
    service, _storage, _root = _service(tmp_path, provider)

    metadata, result = await service.recognize(
        _stream(_encoded_solid_image((11, 2_200))),
        content_type="image/png",
    )

    assert metadata.content_type == "image/png"
    assert result.outcome is ExtractionOutcome.CANDIDATES
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_disallowed_mime_consumes_zero_chunks_and_has_no_side_effects(
    tmp_path: Path,
) -> None:
    consumed = 0

    async def observable_stream() -> AsyncIterator[bytes]:
        nonlocal consumed
        consumed += 1
        yield PNG_SCREENSHOT

    provider = FakeProvider([])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            observable_stream(),
            content_type="application/octet-stream",
        )

    assert exc_info.value.code is ImageRecognitionErrorCode.CONTENT_TYPE_NOT_ALLOWED
    assert consumed == 0
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_stream_failure_is_safe_and_has_no_exception_chain(tmp_path: Path) -> None:
    private_detail = "stream-private-secret"
    provider = FakeProvider([])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            _failing_stream(private_detail),
            content_type="image/png",
        )

    error = exc_info.value
    assert error.code is ImageRecognitionErrorCode.INVALID_REQUEST
    assert error.__context__ is None
    assert error.__cause__ is None
    assert private_detail not in repr(error)
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.parametrize(
    "stage",
    ["validate", "prepare", "clock", "require_aware_utc"],
)
@pytest.mark.asyncio
async def test_unexpected_pre_storage_failure_is_fixed_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stage: str,
) -> None:
    provider = FakeProvider([])
    service, storage, root = _service(tmp_path, provider)
    private_detail = (
        f"preparation-secret {FAKE_FILENAME} {root} "
        f"{base64_marker(PNG_SCREENSHOT)}"
    )
    failure = RuntimeError(private_detail)
    if stage == "validate":
        monkeypatch.setattr(service, "_validate_image", Mock(side_effect=failure))
    elif stage == "prepare":
        monkeypatch.setattr(
            service,
            "_prepare_inference_image",
            Mock(side_effect=failure),
        )
    elif stage == "clock":
        monkeypatch.setattr(service, "_clock", Mock(side_effect=failure))
    else:
        monkeypatch.setattr(
            image_recognition_module,
            "require_aware_utc",
            Mock(side_effect=failure),
        )
    put_private = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(storage, "put_private", put_private)
    monkeypatch.setattr(storage, "delete", delete)

    with caplog.at_level(logging.DEBUG), pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            _stream(PNG_SCREENSHOT),
            content_type="image/png",
            original_filename=FAKE_FILENAME,
        )

    error = exc_info.value
    assert error.code is ImageRecognitionErrorCode.PROCESSING_FAILED
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = f"{error!s}{error!r}{error.to_public_dict()!r}{caplog.text}"
    for private_value in (
        private_detail,
        FAKE_FILENAME,
        str(root),
        base64_marker(PNG_SCREENSHOT),
    ):
        assert private_value not in rendered
    put_private.assert_not_awaited()
    delete.assert_not_awaited()
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_known_pre_storage_image_error_keeps_identity_and_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([])
    service, storage, root = _service(tmp_path, provider)
    known_error = ImageRecognitionError(
        code=ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED
    )
    monkeypatch.setattr(
        service,
        "_validate_image",
        Mock(side_effect=known_error),
    )
    put_private = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(storage, "put_private", put_private)
    monkeypatch.setattr(storage, "delete", delete)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is known_error
    assert exc_info.value.code is ImageRecognitionErrorCode.MODEL_DIMENSIONS_UNSUPPORTED
    put_private.assert_not_awaited()
    delete.assert_not_awaited()
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.parametrize(
    "stage",
    ["validate", "prepare", "clock", "require_aware_utc"],
)
@pytest.mark.asyncio
async def test_pre_storage_cancellation_propagates_same_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    provider = FakeProvider([])
    service, storage, root = _service(tmp_path, provider)
    cancellation = asyncio.CancelledError(f"cancel-{stage}")
    if stage == "validate":
        monkeypatch.setattr(
            service,
            "_validate_image",
            Mock(side_effect=cancellation),
        )
    elif stage == "prepare":
        monkeypatch.setattr(
            service,
            "_prepare_inference_image",
            Mock(side_effect=cancellation),
        )
    elif stage == "clock":
        monkeypatch.setattr(service, "_clock", Mock(side_effect=cancellation))
    else:
        monkeypatch.setattr(
            image_recognition_module,
            "require_aware_utc",
            Mock(side_effect=cancellation),
        )
    put_private = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(storage, "put_private", put_private)
    monkeypatch.setattr(storage, "delete", delete)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is cancellation
    put_private.assert_not_awaited()
    delete.assert_not_awaited()
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_exact_size_boundary_and_one_byte_over(tmp_path: Path) -> None:
    provider = FakeProvider([_response_for(_place())])
    service, _storage, root = _service(
        tmp_path,
        provider,
        max_file_size_bytes=len(PNG_SCREENSHOT),
    )

    metadata, _result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )
    assert metadata.byte_size == len(PNG_SCREENSHOT)
    before = {path.name for path in (root / "objects").iterdir()}

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            _stream(PNG_SCREENSHOT + b"x"),
            content_type="image/png",
        )

    assert exc_info.value.code is ImageRecognitionErrorCode.FILE_TOO_LARGE
    assert len(provider.calls) == 1
    assert {path.name for path in (root / "objects").iterdir()} == before


@pytest.mark.asyncio
async def test_storage_failure_makes_zero_model_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([])
    service, storage, root = _service(tmp_path, provider)
    put_failure = StorageProviderError(code=StorageProviderErrorCode.WRITE_FAILED)
    monkeypatch.setattr(storage, "put_private", AsyncMock(side_effect=put_failure))

    with pytest.raises(StorageProviderError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is put_failure
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_storage_cancellation_propagates_with_zero_model_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([])
    service, storage, root = _service(tmp_path, provider)
    cancellation = asyncio.CancelledError("cancel-storage")
    monkeypatch.setattr(storage, "put_private", AsyncMock(side_effect=cancellation))

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is cancellation
    assert provider.calls == []
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_one_structural_repair_uses_prior_candidate_without_image_payload(
    tmp_path: Path,
) -> None:
    provider = _EvidenceCheckingImageProvider(
        [
            _invalid_candidate_response(),
            _response_for(_place()),
        ]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
        original_filename=FAKE_FILENAME,
    )

    assert result.candidates[0].title == "海边咖啡"
    assert len(provider.calls) == 2
    repair_snapshot = json.dumps(provider.calls[1].messages, ensure_ascii=False)
    assert "data:image/" not in repair_snapshot
    assert ";base64," not in repair_snapshot
    assert base64_marker(PNG_SCREENSHOT) not in repair_snapshot
    assert FAKE_FILENAME not in repair_snapshot
    assert str(_root) not in repair_snapshot
    assert [message["role"] for message in provider.calls[1].messages] == [
        "system",
        "assistant",
        "user",
    ]


@pytest.mark.asyncio
async def test_image_without_prior_candidate_evidence_rejects_new_place(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [
            fake_response(content='{"outcome":"candidates","candidates":[]}'),
            _response_for(_place("上一轮不存在的新地点")),
        ]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert result.candidates == ()
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "forbidden_value",
    [
        "data:image/png;base64,AAAA",
        "/Users/private/source.png",
        r"C:\private\source.jpg",
        "private-source.webp",
        "A" * 300,
    ],
)
@pytest.mark.asyncio
async def test_unsafe_prior_image_evidence_is_never_sent_for_repair(
    tmp_path: Path,
    forbidden_value: str,
) -> None:
    payload = json.loads(
        ExtractionResult.with_candidates((_place(),)).model_dump_json()
    )
    payload["unexpected_private_value"] = forbidden_value
    provider = FakeProvider(
        [
            fake_response(content=json.dumps(payload, ensure_ascii=False)),
            _response_for(_place("不得采用的新地点")),
        ]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_image_and_text_share_semantics_and_explicit_structured_output(
    tmp_path: Path,
) -> None:
    provider = FakeProvider([_response_for(_place())])
    service, _storage, _root = _service(
        tmp_path,
        provider,
        structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
    )

    await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    system_prompt = str(provider.calls[0].messages[0]["content"])
    assert EXTRACTION_SEMANTIC_RULES in system_prompt
    assert provider.calls[0].response_format is not None
    assert provider.calls[0].response_format.mode is StructuredOutputMode.JSON_SCHEMA


@pytest.mark.asyncio
async def test_two_invalid_candidate_responses_return_model_invalid(
    tmp_path: Path,
) -> None:
    response = _invalid_candidate_response()
    provider = FakeProvider([response, response])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        fake_response(content="not json"),
        fake_response(
            tool_calls=(ToolCall(id="call-1", name="forbidden", arguments={}),)
        ),
    ],
)
@pytest.mark.asyncio
async def test_image_response_without_safe_candidate_evidence_stops_stably(
    tmp_path: Path,
    response: ModelResponse,
) -> None:
    provider = FakeProvider([response, _response_for(_place("不得采用的新地点"))])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_repair_provider_error_removes_new_file(tmp_path: Path) -> None:
    provider_error = ProviderError(code=ProviderErrorCode.TIMEOUT)
    provider = FakeProvider([_invalid_candidate_response(), provider_error])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ProviderError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is provider_error
    assert len(provider.calls) == 2
    _assert_no_storage_residue(root)


@pytest.mark.parametrize(
    "code",
    [
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.AUTHENTICATION_FAILED,
        ProviderErrorCode.PROVIDER_ERROR,
    ],
)
@pytest.mark.asyncio
async def test_provider_errors_propagate_and_remove_only_new_file(
    tmp_path: Path,
    code: ProviderErrorCode,
) -> None:
    provider_error = ProviderError(code=code)
    provider = FakeProvider([provider_error])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ProviderError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is provider_error
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_cancelled_error_propagates_and_removes_new_file(tmp_path: Path) -> None:
    cancellation = asyncio.CancelledError("cancel-image-recognition")
    provider = FakeProvider([cancellation])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is cancellation
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_provider_error_cleanup_cancellation_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider([ProviderError(code=ProviderErrorCode.TIMEOUT)])
    service, storage, root = _service(tmp_path, provider)
    cleanup_cancellation = asyncio.CancelledError("cancel-cleanup")
    monkeypatch.setattr(storage, "delete", AsyncMock(side_effect=cleanup_cancellation))

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value is cleanup_cancellation
    assert len(list((root / "objects").iterdir())) == 1


@pytest.mark.asyncio
async def test_private_cleanup_runtime_error_is_fixed_and_does_not_touch_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = FakeProvider([ProviderError(code=ProviderErrorCode.PROVIDER_ERROR)])
    service, storage, root = _service(tmp_path, provider)
    existing = await storage.put_private(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        expires_at=FIXED_NOW + timedelta(days=30),
    )
    private_detail = f"cleanup-secret {FAKE_FILENAME} {root}"
    deleted_keys: list[str] = []

    async def fail_delete(file_key: str) -> None:
        deleted_keys.append(file_key)
        raise RuntimeError(private_detail)

    monkeypatch.setattr(storage, "delete", fail_delete)

    with caplog.at_level(logging.DEBUG), pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(
            _stream(PNG_SCREENSHOT),
            content_type="image/png",
            original_filename=FAKE_FILENAME,
        )

    error = exc_info.value
    assert error.code is ImageRecognitionErrorCode.PROCESSING_FAILED
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = f"{error!s}{error!r}{error.to_public_dict()!r}{caplog.text}"
    assert private_detail not in rendered
    assert FAKE_FILENAME not in rendered
    assert str(root) not in rendered
    assert len(deleted_keys) == 1
    assert deleted_keys[0] != existing.file_key
    assert (await storage.get_private_access(existing.file_key)).file == existing
    assert existing.file_key in {path.name for path in (root / "objects").iterdir()}


@pytest.mark.asyncio
async def test_failure_cleanup_never_deletes_preexisting_file(tmp_path: Path) -> None:
    provider_error = ProviderError(code=ProviderErrorCode.PROVIDER_ERROR)
    provider = FakeProvider([provider_error])
    service, storage, root = _service(tmp_path, provider)
    existing = await storage.put_private(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
        retention_policy=RetentionPolicy.ORIGINAL_SCREENSHOT,
        expires_at=FIXED_NOW + timedelta(days=30),
    )

    with pytest.raises(ProviderError):
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    access = await storage.get_private_access(existing.file_key)
    assert access.file == existing
    assert {path.name for path in (root / "objects").iterdir()} == {
        existing.file_key
    }


@pytest.mark.asyncio
async def test_unexpected_model_failure_is_safe_and_cleans_new_file(
    tmp_path: Path,
) -> None:
    private_detail = "unexpected-model-secret"
    provider = FakeProvider([RuntimeError(private_detail)])
    service, _storage, root = _service(tmp_path, provider)

    with pytest.raises(ImageRecognitionError) as exc_info:
        await service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")

    assert exc_info.value.code is ImageRecognitionErrorCode.PROCESSING_FAILED
    assert private_detail not in str(exc_info.value)
    assert private_detail not in repr(exc_info.value)
    assert private_detail not in repr(exc_info.value.to_public_dict())
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    _assert_no_storage_residue(root)


@pytest.mark.asyncio
async def test_input_chunks_are_not_modified_and_repeated_calls_are_isolated(
    tmp_path: Path,
) -> None:
    chunks = [PNG_SCREENSHOT[:20], PNG_SCREENSHOT[20:]]
    original = list(chunks)
    provider = FakeProvider([_response_for(_place()), _response_for(_place())])
    service, _storage, _root = _service(tmp_path, provider)

    first = await service.recognize(_stream(*chunks), content_type="image/png")
    second = await service.recognize(_stream(*chunks), content_type="image/png")

    assert chunks == original
    assert first[0].file_key != second[0].file_key
    assert first[1] == second[1]
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_calls_have_no_shared_state(tmp_path: Path) -> None:
    count = 12
    provider = FakeProvider([_response_for(_place()) for _ in range(count)])
    service, _storage, root = _service(tmp_path, provider)

    results = await asyncio.gather(
        *(
            service.recognize(_stream(PNG_SCREENSHOT), content_type="image/png")
            for _ in range(count)
        )
    )

    keys = {metadata.file_key for metadata, _result in results}
    assert len(keys) == count
    assert len(list((root / "objects").iterdir())) == count
    assert len(provider.calls) == count


@pytest.mark.asyncio
async def test_sensitive_image_data_and_filename_do_not_leak(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider_error = ProviderError(code=ProviderErrorCode.PROVIDER_ERROR)
    provider = FakeProvider([provider_error])
    service, _storage, root = _service(tmp_path, provider)

    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as exc_info:
        await service.recognize(
            _stream(PNG_SCREENSHOT),
            content_type="image/png",
            original_filename=FAKE_FILENAME,
        )

    public = (
        f"{exc_info.value!s}{exc_info.value!r}"
        f"{exc_info.value.to_public_dict()!r}{caplog.text}"
    )
    assert FAKE_FILENAME not in public
    assert base64_marker(PNG_SCREENSHOT) not in public
    assert str(root) not in public
    assert base64_marker(PNG_SCREENSHOT) not in repr(provider.calls[0])
    _assert_no_storage_residue(root)


def base64_marker(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")[:32]
