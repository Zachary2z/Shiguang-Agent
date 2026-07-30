"""Public HTTP classification for safe screenshot storage failures."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.providers.storage import StorageProviderError, StorageProviderErrorCode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status", "public_code"),
    (
        (
            StorageProviderErrorCode.CONTENT_TYPE_NOT_ALLOWED,
            415,
            "IMAGE_CONTENT_TYPE_NOT_ALLOWED",
        ),
        (
            StorageProviderErrorCode.CONTENT_SIGNATURE_MISMATCH,
            422,
            "IMAGE_CONTENT_SIGNATURE_MISMATCH",
        ),
        (StorageProviderErrorCode.FILE_EMPTY, 400, "IMAGE_FILE_EMPTY"),
        (StorageProviderErrorCode.FILE_TOO_LARGE, 413, "IMAGE_FILE_TOO_LARGE"),
        (StorageProviderErrorCode.WRITE_FAILED, 500, "STORAGE_WRITE_FAILED"),
        (StorageProviderErrorCode.CORRUPT_OBJECT, 500, "STORAGE_CORRUPT_OBJECT"),
    ),
)
async def test_storage_errors_have_stable_safe_http_classes(
    code: StorageProviderErrorCode,
    status: int,
    public_code: str,
) -> None:
    api = FastAPI()
    install_error_handlers(api)

    @api.get("/storage-error")
    async def fail() -> None:
        raise StorageProviderError(code=code)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/storage-error")

    assert response.status_code == status
    assert response.json()["error_code"] == public_code
    assert response.json()["message"] == "The screenshot could not be prepared."
    expected_actions = (
        ["reupload_image", "supply_text"]
        if status < 500
        else ["retry_later", "supply_text"]
    )
    assert response.json()["recovery_actions"] == expected_actions
    rendered = response.text
    for private in ("filename", "/private/path", "storage implementation", "traceback"):
        assert private not in rendered.lower()
