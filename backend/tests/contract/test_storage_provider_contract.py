"""Provider-neutral contract coverage for private file storage."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.providers import (
    PrivateAccessMethod,
    PrivateFileAccess,
    PrivateFileDeleteResult,
    PrivateFileMetadata,
    RetentionPolicy,
    StorageProvider,
    StorageProviderError,
    StorageProviderErrorCode,
)

VALID_KEY = "A" * 43
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _metadata(**changes: object) -> PrivateFileMetadata:
    values: dict[str, object] = {
        "file_key": VALID_KEY,
        "created_at": NOW,
        "byte_size": 12,
        "content_type": "image/png",
        "retention_policy": RetentionPolicy.ORIGINAL_SCREENSHOT,
        "expires_at": NOW + timedelta(days=30),
        "content_sha256": "a" * 64,
    }
    values.update(changes)
    return PrivateFileMetadata(**values)  # type: ignore[arg-type]


def test_storage_provider_has_one_minimal_private_contract() -> None:
    methods = {
        name
        for name, member in inspect.getmembers(StorageProvider, inspect.isfunction)
        if getattr(member, "__isabstractmethod__", False)
    }

    assert methods == {"put_private", "read_private", "get_private_access", "delete"}


def test_private_metadata_contains_lifecycle_fields_without_a_path_or_url() -> None:
    metadata = _metadata()
    public = metadata.model_dump(mode="json")

    assert public == {
        "file_key": VALID_KEY,
        "created_at": "2026-07-22T12:00:00Z",
        "byte_size": 12,
        "content_type": "image/png",
        "retention_policy": "original_screenshot_30_days",
        "expires_at": "2026-08-21T12:00:00Z",
        "content_sha256": "a" * 64,
    }
    assert not ({"path", "absolute_path", "url", "filename"} & public.keys())


def test_private_access_explicitly_requires_a_future_application_route() -> None:
    access = PrivateFileAccess(
        file=_metadata(),
        method=PrivateAccessMethod.APPLICATION_DOWNLOAD_ROUTE_REQUIRED,
    )

    public = access.model_dump(mode="json")
    serialized = str(public)
    assert public["method"] == "application_download_route_required"
    assert "file://" not in serialized
    assert "http://" not in serialized
    assert "https://" not in serialized


@pytest.mark.parametrize(
    "file_key",
    [
        "",
        "A" * 31,
        "A" * 129,
        "../" + "A" * 32,
        "/" + "A" * 32,
        "A/B" + "C" * 32,
        "A\\B" + "C" * 32,
        "." * 32,
        "Ａ" * 32,
        "A" * 31 + "\u2024",
    ],
)
def test_metadata_and_delete_results_reject_non_opaque_keys(file_key: str) -> None:
    with pytest.raises(ValidationError):
        _metadata(file_key=file_key)
    with pytest.raises(ValidationError):
        PrivateFileDeleteResult(file_key=file_key, deleted=False)


def test_lifecycle_metadata_requires_positive_size_and_future_expiration() -> None:
    with pytest.raises(ValidationError):
        _metadata(byte_size=0)
    with pytest.raises(ValidationError):
        _metadata(expires_at=NOW)
    with pytest.raises(ValidationError):
        _metadata(created_at=datetime(2026, 7, 22, 12, 0), expires_at=None)


@pytest.mark.parametrize("code", tuple(StorageProviderErrorCode))
def test_storage_errors_have_stable_safe_public_shapes(
    code: StorageProviderErrorCode,
) -> None:
    error = StorageProviderError(code=code)
    public = error.to_public_dict()

    assert public["code"] == code.value
    assert public["summary"] == str(error)
    assert set(public) == {"code", "summary", "retryable"}
    assert "path" not in str(public).lower()
    assert "filename" not in str(public).lower()


def test_storage_error_rejects_untyped_codes() -> None:
    with pytest.raises(TypeError, match="StorageProviderErrorCode"):
        StorageProviderError(code="STORAGE_WRITE_FAILED")  # type: ignore[arg-type]
