"""Strict, mutually exclusive inputs for the single collection workflow."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.application.text_extraction import MAX_TEXT_INPUT_CHARS


class _InputModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class TextInput(_InputModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=MAX_TEXT_INPUT_CHARS, repr=False)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text cannot be blank")
        return value


class UrlInput(_InputModel):
    type: Literal["url"] = "url"
    url: str = Field(min_length=1, max_length=2048, repr=False)

    @field_validator("url")
    @classmethod
    def require_http_url_without_credentials(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            valid = (
                parts.scheme in {"http", "https"}
                and bool(parts.hostname)
                and parts.username is None
                and parts.password is None
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("url must be an HTTP(S) URL without credentials")
        return value


class ImageInput(_InputModel):
    type: Literal["image"] = "image"
    content_type: str = Field(min_length=1, max_length=127)
    payload: bytes = Field(min_length=1, repr=False)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)
    supplemental_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TEXT_INPUT_CHARS,
        repr=False,
    )

    @field_validator("content_type")
    @classmethod
    def normalize_content_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or ";" in normalized or "/" not in normalized:
            raise ValueError("content_type must be a normalized media type")
        return normalized

    @field_validator("content_sha256")
    @classmethod
    def require_matching_digest(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        payload = data.get("payload") if isinstance(data, dict) else None
        if isinstance(payload, bytes) and hashlib.sha256(payload).hexdigest() != value:
            raise ValueError("content_sha256 must match payload")
        return value

    @field_validator("supplemental_text")
    @classmethod
    def reject_blank_supplemental_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("supplemental_text cannot be blank")
        return value

    @classmethod
    def from_bytes(
        cls,
        payload: bytes,
        *,
        content_type: str,
        supplemental_text: str | None = None,
    ) -> ImageInput:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        return cls(
            content_type=content_type,
            payload=payload,
            content_sha256=hashlib.sha256(payload).hexdigest(),
            supplemental_text=supplemental_text,
        )

    def message_content(self) -> str:
        """Persist only bounded association metadata, never image bytes or paths."""

        return json.dumps(
            {
                "content_sha256": self.content_sha256,
                "content_type": self.content_type,
                "supplemental_text": self.supplemental_text,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def supplemental_text_from_message(content: str) -> str | None:
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(value, dict):
            return None
        supplemental = value.get("supplemental_text")
        return supplemental if isinstance(supplemental, str) and supplemental.strip() else None


CollectionInput = Annotated[TextInput | UrlInput | ImageInput, Field(discriminator="type")]
COLLECTION_INPUT_ADAPTER: TypeAdapter[CollectionInput] = TypeAdapter(CollectionInput)


__all__ = [
    "COLLECTION_INPUT_ADAPTER",
    "CollectionInput",
    "ImageInput",
    "TextInput",
    "UrlInput",
]
