"""Single source of truth for opaque application identifiers."""

from __future__ import annotations

import re
import secrets

TRACE_ID_PATTERN = re.compile(r"^trc_[A-Za-z0-9_-]{32}$")

_OPAQUE_ID_PATTERNS = {
    "arn": re.compile(r"^arn_[a-f0-9]{32}$"),
    "tlr": re.compile(r"^tlr_[a-f0-9]{32}$"),
    "usr": re.compile(r"^usr_[a-f0-9]{32}$"),
    "ses": re.compile(r"^ses_[a-f0-9]{32}$"),
    "msg": re.compile(r"^msg_[a-f0-9]{32}$"),
    "src": re.compile(r"^src_[a-f0-9]{32}$"),
    "col": re.compile(r"^col_[a-f0-9]{32}$"),
    "cwo": re.compile(r"^cwo_[a-f0-9]{32}$"),
    "pln": re.compile(r"^pln_[a-f0-9]{32}$"),
    "pit": re.compile(r"^pit_[a-f0-9]{32}$"),
    "apr": re.compile(r"^apr_[a-f0-9]{32}$"),
}


def generate_trace_id() -> str:
    """Generate a 192-bit, URL-safe and non-sequential trace identifier."""

    return f"trc_{secrets.token_urlsafe(24)}"


def validate_trace_id(value: str) -> str:
    if not isinstance(value, str) or TRACE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("trace_id must be trc_ followed by 32 URL-safe characters")
    return value


def generate_agent_run_id() -> str:
    return _generate_opaque_id("arn")


def generate_tool_run_id() -> str:
    return _generate_opaque_id("tlr")


def generate_user_id() -> str:
    return _generate_opaque_id("usr")


def generate_session_id() -> str:
    return _generate_opaque_id("ses")


def generate_message_id() -> str:
    return _generate_opaque_id("msg")


def generate_source_id() -> str:
    return _generate_opaque_id("src")


def generate_collection_item_id() -> str:
    return _generate_opaque_id("col")


def generate_collection_write_operation_id() -> str:
    return _generate_opaque_id("cwo")


def generate_plan_id() -> str:
    return _generate_opaque_id("pln")


def generate_plan_item_id() -> str:
    return _generate_opaque_id("pit")


def generate_approval_id() -> str:
    return _generate_opaque_id("apr")


def validate_agent_run_id(value: str) -> str:
    return _validate_opaque_id(value, "arn", "agent_run_id")


def validate_tool_run_id(value: str) -> str:
    return _validate_opaque_id(value, "tlr", "tool_run_id")


def validate_user_id(value: str) -> str:
    return _validate_opaque_id(value, "usr", "user_id")


def validate_session_id(value: str) -> str:
    return _validate_opaque_id(value, "ses", "session_id")


def validate_message_id(value: str) -> str:
    return _validate_opaque_id(value, "msg", "message_id")


def validate_source_id(value: str) -> str:
    return _validate_opaque_id(value, "src", "source_id")


def validate_collection_item_id(value: str) -> str:
    return _validate_opaque_id(value, "col", "collection_item_id")


def validate_collection_write_operation_id(value: str) -> str:
    return _validate_opaque_id(value, "cwo", "collection_write_operation_id")


def validate_plan_id(value: str) -> str:
    return _validate_opaque_id(value, "pln", "plan_id")


def validate_plan_item_id(value: str) -> str:
    return _validate_opaque_id(value, "pit", "plan_item_id")


def validate_approval_id(value: str) -> str:
    return _validate_opaque_id(value, "apr", "approval_id")


def _generate_opaque_id(prefix: str) -> str:
    """Generate a 128-bit lowercase identifier for a known namespace."""

    if prefix not in _OPAQUE_ID_PATTERNS:
        raise ValueError("unknown identifier namespace")
    return f"{prefix}_{secrets.token_hex(16)}"


def _validate_opaque_id(value: str, prefix: str, field_name: str) -> str:
    pattern = _OPAQUE_ID_PATTERNS[prefix]
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be {prefix}_ followed by 32 lowercase hexadecimal characters"
        )
    if len(set(value[4:])) == 1:
        raise ValueError(f"{field_name} payload is not sufficiently opaque")
    return value
