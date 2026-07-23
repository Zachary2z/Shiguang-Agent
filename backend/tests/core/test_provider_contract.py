from __future__ import annotations

import asyncio
import json

import pytest

from nanobot_core.agent import AgentRunner
from nanobot_core.providers import (
    FinishReason,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    StructuredOutputMode,
    TokenUsage,
    ToolCall,
)
from nanobot_core.tools import ToolRegistry
from tests.core.fakes import FakeProvider


def test_text_response_carries_complete_provider_metadata() -> None:
    response = ModelResponse(
        model_name="fixture-text-model",
        usage=TokenUsage(input_tokens=12, output_tokens=5, total_tokens=17),
        latency_ms=240,
        finish_reason=FinishReason.STOP,
        provider_request_id="request-text-001",
        content="A complete answer.",
    )

    assert response.model_name == "fixture-text-model"
    assert response.usage == TokenUsage(input_tokens=12, output_tokens=5, total_tokens=17)
    assert response.latency_ms == 240
    assert response.finish_reason is FinishReason.STOP
    assert response.provider_request_id == "request-text-001"
    assert response.content == "A complete answer."
    assert response.tool_calls == []


def test_tool_calling_response_carries_the_same_provider_metadata() -> None:
    tool_call = ToolCall("call-001", "lookup", {"query": "深圳"})
    response = ModelResponse(
        model_name="fixture-tool-model",
        usage=TokenUsage(input_tokens=20, output_tokens=8, total_tokens=28),
        latency_ms=310,
        finish_reason=FinishReason.TOOL_CALLS,
        provider_request_id="request-tool-001",
        tool_calls=[tool_call],
    )

    assert response.model_name == "fixture-tool-model"
    assert response.usage.total_tokens == 28
    assert response.latency_ms == 310
    assert response.finish_reason is FinishReason.TOOL_CALLS
    assert response.provider_request_id == "request-tool-001"
    assert response.tool_calls == [tool_call]


def test_token_usage_allows_unknown_and_zero_values() -> None:
    assert TokenUsage() == TokenUsage(
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
    )
    assert TokenUsage(input_tokens=0, output_tokens=0) == TokenUsage(
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )
    assert TokenUsage(total_tokens=0).total_tokens == 0


def test_structured_output_rejects_invalid_provider_neutral_configuration() -> None:
    with pytest.raises(ValueError, match="requires a non-empty"):
        StructuredOutput(
            mode=StructuredOutputMode.JSON_SCHEMA,
            schema_name="result",
            json_schema={},
        )
    with pytest.raises(ValueError, match="safe schema name"):
        StructuredOutput(
            mode=StructuredOutputMode.JSON_SCHEMA,
            schema_name="private schema text",
            json_schema={"type": "object"},
        )
    with pytest.raises(ValueError, match="does not accept"):
        StructuredOutput(
            mode=StructuredOutputMode.JSON_OBJECT,
            json_schema={"type": "object"},
        )


@pytest.mark.asyncio
async def test_fake_provider_records_isolated_structured_output_snapshots() -> None:
    response = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(),
        latency_ms=0,
        finish_reason=FinishReason.STOP,
        content="{}",
    )
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    response_format = StructuredOutput(
        mode=StructuredOutputMode.JSON_SCHEMA,
        schema_name="result",
        json_schema=schema,
    )
    provider = FakeProvider([response])

    await provider.chat(messages=[], tools=None, response_format=response_format)
    schema["properties"] = {}

    recorded = provider.calls[0].response_format
    assert recorded is not None
    assert recorded is not response_format
    assert recorded.json_schema == {
        "type": "object",
        "properties": {"value": {"type": "string"}},
    }


def test_token_usage_derives_total_when_both_parts_are_known() -> None:
    usage = TokenUsage(input_tokens=7, output_tokens=3)

    assert usage.total_tokens == 10


@pytest.mark.parametrize("field_name", ["input_tokens", "output_tokens", "total_tokens"])
@pytest.mark.parametrize("invalid_value", [-1, True])
def test_token_usage_rejects_negative_and_boolean_counts(
    field_name: str,
    invalid_value: int | bool,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        TokenUsage(**{field_name: invalid_value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": 3, "output_tokens": 4, "total_tokens": 6},
        {"input_tokens": 5, "total_tokens": 4},
        {"output_tokens": 5, "total_tokens": 4},
    ],
)
def test_token_usage_rejects_inconsistent_totals(usage: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        TokenUsage(**usage)  # type: ignore[arg-type]


@pytest.mark.parametrize("latency_ms", [-1, True])
def test_model_response_rejects_invalid_latency(latency_ms: int | bool) -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        ModelResponse(
            model_name="fixture-model",
            usage=TokenUsage(),
            latency_ms=latency_ms,
            finish_reason=FinishReason.STOP,
        )


@pytest.mark.parametrize("model_name", ["", "  ", "\n"])
def test_model_response_rejects_blank_model_names(model_name: str) -> None:
    with pytest.raises(ValueError, match="model_name"):
        ModelResponse(
            model_name=model_name,
            usage=TokenUsage(),
            latency_ms=0,
            finish_reason=FinishReason.STOP,
        )


def test_model_response_rejects_provider_specific_finish_reason_strings() -> None:
    with pytest.raises(TypeError, match="FinishReason"):
        ModelResponse(
            model_name="fixture-model",
            usage=TokenUsage(),
            latency_ms=0,
            finish_reason="vendor_stop",  # type: ignore[arg-type]
        )


def test_provider_request_id_has_explicit_missing_and_present_semantics() -> None:
    missing = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(),
        latency_ms=0,
        finish_reason=FinishReason.STOP,
    )
    present = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(),
        latency_ms=0,
        finish_reason=FinishReason.STOP,
        provider_request_id="request-001",
    )

    assert missing.provider_request_id is None
    assert present.provider_request_id == "request-001"

    with pytest.raises(ValueError, match="provider_request_id"):
        ModelResponse(
            model_name="fixture-model",
            usage=TokenUsage(),
            latency_ms=0,
            finish_reason=FinishReason.STOP,
            provider_request_id="  ",
        )


@pytest.mark.parametrize(
    "finish_reason",
    [
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
        FinishReason.UNKNOWN,
    ],
)
def test_non_tool_finish_reasons_are_provider_neutral(finish_reason: FinishReason) -> None:
    response = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(),
        latency_ms=0,
        finish_reason=finish_reason,
    )

    assert response.finish_reason is finish_reason


@pytest.mark.parametrize(
    ("finish_reason", "tool_calls"),
    [
        (FinishReason.STOP, [ToolCall("call-001", "lookup", {})]),
        (FinishReason.TOOL_CALLS, []),
    ],
)
def test_model_response_rejects_inconsistent_tool_finish_reason(
    finish_reason: FinishReason,
    tool_calls: list[ToolCall],
) -> None:
    with pytest.raises(ValueError, match="tool_calls"):
        ModelResponse(
            model_name="fixture-model",
            usage=TokenUsage(),
            latency_ms=0,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        (ProviderErrorCode.TIMEOUT, True),
        (ProviderErrorCode.RATE_LIMITED, True),
        (ProviderErrorCode.AUTHENTICATION_FAILED, False),
        (ProviderErrorCode.INVALID_RESPONSE, False),
        (ProviderErrorCode.PROVIDER_ERROR, False),
    ],
)
def test_provider_errors_have_typed_codes_and_stable_retry_semantics(
    code: ProviderErrorCode,
    retryable: bool,
) -> None:
    error = ProviderError(code=code)

    assert error.code is code
    assert error.retryable is retryable
    assert error.summary.startswith("The model provider")
    assert str(error) == error.summary


def test_rate_limit_error_supports_retry_after() -> None:
    error = ProviderError(
        code=ProviderErrorCode.RATE_LIMITED,
        retry_after_seconds=2.5,
    )

    assert error.retry_after_seconds == 2.5

    with pytest.raises(ValueError, match="only valid for rate-limited"):
        ProviderError(
            code=ProviderErrorCode.TIMEOUT,
            retry_after_seconds=1,
        )


@pytest.mark.parametrize("invalid_value", [-1, True, float("inf"), float("nan")])
def test_retry_after_rejects_invalid_values(invalid_value: float | bool) -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        ProviderError(
            code=ProviderErrorCode.RATE_LIMITED,
            retry_after_seconds=invalid_value,
        )


def test_public_error_serialization_excludes_raw_exception_and_sensitive_data() -> None:
    try:
        try:
            raise RuntimeError(
                "Authorization: Bearer api-key-secret; full raw response; internal stack"
            )
        except RuntimeError as cause:
            raise ProviderError(
                code=ProviderErrorCode.PROVIDER_ERROR,
            ) from cause
    except ProviderError as error:
        serialized = json.dumps(error.to_public_dict(), sort_keys=True)

    assert json.loads(serialized) == {
        "code": "PROVIDER_ERROR",
        "retry_after_seconds": None,
        "retryable": False,
        "summary": "The model provider request failed.",
    }
    assert "api-key-secret" not in serialized
    assert "Authorization" not in serialized
    assert "full raw response" not in serialized
    assert "internal stack" not in serialized


@pytest.mark.asyncio
async def test_fake_provider_sequences_text_tool_calls_and_every_error() -> None:
    text_response = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(input_tokens=1, output_tokens=1),
        latency_ms=1,
        finish_reason=FinishReason.STOP,
        content="done",
    )
    tool_response = ModelResponse(
        model_name="fixture-model",
        usage=TokenUsage(input_tokens=2, output_tokens=1),
        latency_ms=2,
        finish_reason=FinishReason.TOOL_CALLS,
        tool_calls=[ToolCall("call-001", "lookup", {})],
    )
    errors = [
        ProviderError(code=code)
        for code in ProviderErrorCode
    ]
    provider = FakeProvider([text_response, tool_response, *errors])

    assert await provider.chat(messages=[], tools=None) is text_response
    assert await provider.chat(messages=[], tools=None) is tool_response
    for expected_error in errors:
        with pytest.raises(ProviderError) as raised:
            await provider.chat(messages=[], tools=None)
        assert raised.value is expected_error


@pytest.mark.asyncio
async def test_fake_provider_retains_independent_message_and_tool_snapshots() -> None:
    provider = FakeProvider(
        [
            ModelResponse(
                model_name="fixture-model",
                usage=TokenUsage(),
                latency_ms=0,
                finish_reason=FinishReason.STOP,
                content="done",
            )
        ]
    )
    messages = [{"role": "user", "content": {"parts": ["before"]}}]
    tools = [{"type": "function", "function": {"name": "lookup"}}]

    await provider.chat(messages=messages, tools=tools)
    messages[0]["content"]["parts"].append("after")
    tools[0]["function"]["name"] = "changed"

    assert provider.calls[0].messages == [
        {"role": "user", "content": {"parts": ["before"]}}
    ]
    assert provider.calls[0].tools == [
        {"type": "function", "function": {"name": "lookup"}}
    ]


@pytest.mark.asyncio
async def test_runner_propagates_typed_provider_errors_without_string_parsing() -> None:
    error = ProviderError(
        code=ProviderErrorCode.AUTHENTICATION_FAILED,
    )

    with pytest.raises(ProviderError) as raised:
        await AgentRunner(FakeProvider([error]), ToolRegistry()).run([])

    assert raised.value is error
    assert raised.value.code is ProviderErrorCode.AUTHENTICATION_FAILED
    assert raised.value.retryable is False


@pytest.mark.asyncio
async def test_runner_does_not_swallow_asyncio_cancellation() -> None:
    cancellation = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError) as raised:
        await AgentRunner(FakeProvider([cancellation]), ToolRegistry()).run([])

    assert raised.value is cancellation
