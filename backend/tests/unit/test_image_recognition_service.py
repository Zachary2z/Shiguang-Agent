"""Offline M0-4C screenshot validation, lifecycle, and extraction tests."""

from __future__ import annotations

import asyncio
import base64
import logging
import struct
import zlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.application.image_recognition import (
    MAX_IMAGE_WIDTH,
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
from nanobot_core.providers import ModelResponse, ProviderError, ProviderErrorCode, ToolCall
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
            CandidateField.PRICE,
            CandidateField.TAGS,
        ),
    )


def _response_for(*candidates: PlaceCandidate | EventCandidate) -> ModelResponse:
    payload = ExtractionResult.with_candidates(tuple(candidates)).model_dump_json()
    return fake_response(content=payload)


def _assert_no_storage_residue(root: Path) -> None:
    for child in ("objects", "metadata", ".tmp", ".reservations"):
        assert list((root / child).iterdir()) == []


def _png_with_dimensions(width: int, height: int) -> bytes:
    payload = bytearray(PNG_SCREENSHOT)
    payload[16:20] = struct.pack(">I", width)
    payload[20:24] = struct.pack(">I", height)
    payload[29:33] = struct.pack(">I", zlib.crc32(payload[12:29]) & 0xFFFFFFFF)
    return bytes(payload)


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
async def test_one_structural_repair_can_succeed(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            fake_response(content="not json"),
            _response_for(_place("修复后的店")),
        ]
    )
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.candidates[0].title == "修复后的店"
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
async def test_two_invalid_or_tool_responses_return_model_invalid(
    tmp_path: Path,
    response: ModelResponse,
) -> None:
    provider = FakeProvider([response, response])
    service, _storage, _root = _service(tmp_path, provider)

    _metadata, result = await service.recognize(
        _stream(PNG_SCREENSHOT),
        content_type="image/png",
    )

    assert result.outcome is ExtractionOutcome.MODEL_INVALID_OUTPUT
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_repair_provider_error_removes_new_file(tmp_path: Path) -> None:
    provider_error = ProviderError(code=ProviderErrorCode.TIMEOUT)
    provider = FakeProvider([fake_response(content="not json"), provider_error])
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
