"""Validated creation input independent from execution and persistence implementations."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.identifiers import validate_trace_id

SAFE_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class AgentRunCreate(BaseModel):
    """Validated input for creating the queued application run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    trace_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    intent: str = Field(min_length=1, max_length=64)
    workflow: str = Field(min_length=1, max_length=64)

    @field_validator("trace_id")
    @classmethod
    def validate_optional_trace_id(cls, value: str | None) -> str | None:
        return None if value is None else validate_trace_id(value)

    @field_validator("user_id", "session_id", "intent", "workflow")
    @classmethod
    def validate_safe_label(cls, value: str | None) -> str | None:
        if value is not None and SAFE_LABEL_PATTERN.fullmatch(value) is None:
            raise ValueError("identifier must contain only safe identifier characters")
        return value
