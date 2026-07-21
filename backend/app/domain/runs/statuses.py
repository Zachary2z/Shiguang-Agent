"""Run status and transition contracts with no infrastructure dependency."""

from enum import StrEnum


class AgentRunStatus(StrEnum):
    """The only application status contract for an AgentRun."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolRunStatus(StrEnum):
    """The only application status contract for a ToolRun."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class RunErrorCode(StrEnum):
    """Stable run-level failures not already owned by Provider or Tool contracts."""

    EMPTY_RESPONSE = "RUN_EMPTY_RESPONSE"
    MAX_ITERATIONS = "RUN_MAX_ITERATIONS"
    TOOL_CALL_LIMIT = "RUN_TOOL_CALL_LIMIT"
    REPEATED_TOOL_CALL = "RUN_REPEATED_TOOL_CALL"
    TIMEOUT = "RUN_TIMEOUT"
    CANCELLED = "RUN_CANCELLED"
    INTERNAL_ERROR = "RUN_INTERNAL_ERROR"


TERMINAL_AGENT_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.PARTIALLY_SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

_ALLOWED_TRANSITIONS = {
    AgentRunStatus.QUEUED: frozenset({AgentRunStatus.RUNNING}),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.WAITING_USER,
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.PARTIALLY_SUCCEEDED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.WAITING_USER: frozenset(
        {AgentRunStatus.RUNNING, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}
    ),
}


def ensure_run_transition(current: AgentRunStatus, target: AgentRunStatus) -> None:
    """Reject state regressions while allowing an idempotent same-state write."""

    if current is target:
        return
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"illegal AgentRun transition: {current.value} -> {target.value}")
