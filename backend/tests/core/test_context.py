from __future__ import annotations

from copy import deepcopy

import pytest

from nanobot_core.agent import AgentContext


def test_context_builds_system_explicit_history_and_user_messages() -> None:
    explicit = ({"role": "system", "content": "Extra constraint."},)
    history = [{"role": "assistant", "content": "Earlier answer."}]
    original_history = deepcopy(history)
    context = AgentContext(system_prompt="System prompt.", messages=explicit)

    messages = context.build_messages(user_message="  New question.  ", history=history)

    assert messages == [
        {"role": "system", "content": "System prompt."},
        {"role": "system", "content": "Extra constraint."},
        {"role": "assistant", "content": "Earlier answer."},
        {"role": "user", "content": "New question."},
    ]
    assert history == original_history


@pytest.mark.parametrize("user_message", ["", " ", "\n\t"])
def test_context_rejects_empty_user_messages(user_message: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        AgentContext().build_messages(user_message=user_message)


def test_default_context_contains_no_filesystem_memory_or_business_prompt() -> None:
    prompt = AgentContext().system_prompt.lower()

    for forbidden in (
        "workspace",
        "file",
        "markdown",
        "memory",
        "remember",
        "database",
        "fastapi",
        "收藏",
        "高德",
        "规划",
    ):
        assert forbidden not in prompt
