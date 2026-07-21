"""Opaque run identifiers shared without importing execution-core types."""

import re
import secrets

TRACE_ID_PATTERN = re.compile(r"^trc_[A-Za-z0-9_-]{32}$")


def generate_trace_id() -> str:
    """Generate a 192-bit, URL-safe and non-sequential trace identifier."""

    return f"trc_{secrets.token_urlsafe(24)}"


def validate_trace_id(value: str) -> str:
    if not isinstance(value, str) or TRACE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("trace_id must be trc_ followed by 32 URL-safe characters")
    return value


def generate_agent_run_id() -> str:
    return f"arn_{secrets.token_hex(16)}"


def generate_tool_run_id() -> str:
    return f"tlr_{secrets.token_hex(16)}"
