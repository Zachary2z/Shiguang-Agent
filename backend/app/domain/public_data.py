"""One safety boundary for durable data that may reach public responses or logs."""

from __future__ import annotations

import json
import math
import re
from pathlib import PurePath
from typing import Any

_BASE64_BLOB = re.compile(r"^[A-Za-z0-9+/]{64,}={0,2}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "base64",
        "cookie",
        "file_key",
        "full_prompt",
        "model_response",
        "password",
        "path",
        "prompt",
        "secret",
        "token",
    }
)


def validate_safe_public_data(
    value: dict[str, Any],
    *,
    maximum_bytes: int,
) -> dict[str, Any]:
    """Reject secrets, private paths, large blobs, and unbounded nested content."""

    if not isinstance(value, dict):
        raise ValueError("public data must be an object")
    _validate_safe_value(value)
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError("public data exceeds its safe size limit")
    return value


def _validate_safe_value(value: Any) -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("public data numbers must be finite")
        return
    if isinstance(value, str):
        if len(value) > 512:
            raise ValueError("public data strings are too long")
        lowered = value.casefold()
        if (
            "bearer " in lowered
            or "authorization:" in lowered
            or "cookie:" in lowered
            or "base64" in lowered
            or _BASE64_BLOB.fullmatch(value) is not None
            or value.startswith(("/", "~"))
            or PurePath(value).is_absolute()
        ):
            raise ValueError("public data contains private or credential material")
        return
    if isinstance(value, list):
        if len(value) > 50:
            raise ValueError("public data arrays are too large")
        for item in value:
            _validate_safe_value(item)
        return
    if isinstance(value, dict):
        if len(value) > 50:
            raise ValueError("public data objects are too large")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("public data keys must be bounded strings")
            normalized = key.casefold().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError("public data contains a forbidden field")
            _validate_safe_value(item)
        return
    raise ValueError("public data contains an unsupported value")


__all__ = ["validate_safe_public_data"]
