"""Public HTTP classification for safe location-matching failures."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.providers.map import MapProviderError, MapProviderErrorCode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status"),
    (
        (MapProviderErrorCode.TIMEOUT, 504),
        (MapProviderErrorCode.RATE_LIMITED, 429),
        (MapProviderErrorCode.AUTHENTICATION_FAILED, 503),
        (MapProviderErrorCode.UNAVAILABLE, 503),
        (MapProviderErrorCode.INVALID_REQUEST, 422),
        (MapProviderErrorCode.POI_NOT_FOUND, 502),
        (MapProviderErrorCode.INVALID_RESPONSE, 502),
    ),
)
async def test_location_matching_errors_are_safe_and_recoverable(
    code: MapProviderErrorCode,
    status: int,
) -> None:
    api = FastAPI()
    install_error_handlers(api)

    @api.patch("/location-error")
    async def fail() -> None:
        raise MapProviderError(code=code)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.patch("/location-error")

    assert response.status_code == status
    assert response.json() == {
        "error_code": code.value,
        "message": (
            "Location details may have been saved, but matching did not complete."
        ),
        "recovery_actions": ["reload_collection", "retry_location_match"],
    }
    rendered = response.text.lower()
    for private in (
        "api key",
        "authorization",
        "cookie",
        "provider response",
        "private",
        "traceback",
    ):
        assert private not in rendered
