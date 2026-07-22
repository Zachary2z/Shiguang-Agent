"""Central file-content policy shared by storage configuration and adapters."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

DEFAULT_STORAGE_MAX_FILE_SIZE_BYTES: Final = 10_000_000
MAX_STORAGE_MAX_FILE_SIZE_BYTES: Final = 20_000_000

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_WEBP_RIFF_SIGNATURE = b"RIFF"
_WEBP_FORMAT_SIGNATURE = b"WEBP"

SUPPORTED_STORAGE_CONTENT_TYPES: Final = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
DEFAULT_STORAGE_ALLOWED_CONTENT_TYPES: Final = tuple(
    sorted(SUPPORTED_STORAGE_CONTENT_TYPES)
)
STORAGE_SIGNATURE_PROBE_BYTES: Final = 12

# Public only as an immutable description for configuration and contract tests. Adapters use
# ``content_signature_matches`` so signature rules are not copied into callers.
STORAGE_SIGNATURE_PREFIXES: Final = MappingProxyType(
    {
        "image/jpeg": (_JPEG_SIGNATURE,),
        "image/png": (_PNG_SIGNATURE,),
        "image/webp": (_WEBP_RIFF_SIGNATURE, _WEBP_FORMAT_SIGNATURE),
    }
)


def content_signature_matches(*, content_type: str, prefix: bytes) -> bool:
    """Apply the minimum centralized signature check for an allowed image type."""

    if content_type == "image/png":
        return prefix.startswith(_PNG_SIGNATURE)
    if content_type == "image/jpeg":
        return prefix.startswith(_JPEG_SIGNATURE)
    if content_type == "image/webp":
        return (
            len(prefix) >= STORAGE_SIGNATURE_PROBE_BYTES
            and prefix.startswith(_WEBP_RIFF_SIGNATURE)
            and prefix[8:12] == _WEBP_FORMAT_SIGNATURE
        )
    return False
