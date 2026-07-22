"""Offline contract tests for the application-layer model provider."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable, Sequence
from copy import deepcopy

import httpx
import pytest
import pytest_asyncio
from openai import APIResponseValidationError

from app.config import Settings
from app.providers import OpenAICompatibleProvider
from nanobot_core.agent import AgentRunner
from nanobot_core.providers import FinishReason, ProviderError, ProviderErrorCode
from nanobot_core.tools import ToolRegistry
from tests.core.fakes import EchoTool

FAKE_API_KEY = "fake-unit-test-api-key-do-not-use"
FAKE_BASE_URL = "https://model.example.test/compatible-mode/v1"
FAKE_MODEL = "configured-test-model"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "sqlite+aiosqlite:///:memory:",
        "model_api_base": FAKE_BASE_URL,
        "model_api_key": FAKE_API_KEY,
        "model_name": FAKE_MODEL,
        "model_timeout_seconds": 7,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _completion(
    *,
    content: object = "hello",
    finish_reason: str = "stop",
    model: str = "response-model",
    tool_calls: list[dict[str, object]] | None = None,
    usage: object = ...,
) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                },
            }
        ],
    }
    if usage is ...:
        body["usage"] = {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        }
    elif usage is not None:
        body["usage"] = usage
    return body


def _response(
    body: dict[str, object] | None = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    if body is None:
        body = {"error": {"message": "fake-sensitive-provider-body"}}
    return httpx.Response(status_code, json=body, headers=headers)


class OfflineProviderFactory:
    def __init__(self) -> None:
        self.providers: list[OpenAICompatibleProvider] = []
        self.requests: list[list[httpx.Request]] = []

    def build(
        self,
        outcomes: Sequence[httpx.Response | BaseException],
        *,
        clock: Callable[[], float] | None = None,
    ) -> tuple[OpenAICompatibleProvider, list[httpx.Request]]:
        pending = deque(outcomes)
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if not pending:
                raise AssertionError("mock transport has no outcome left")
            outcome = pending.popleft()
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        kwargs: dict[str, object] = {"http_client": http_client}
        if clock is not None:
            kwargs["clock"] = clock
        provider = OpenAICompatibleProvider.from_settings(
            _settings(),
            **kwargs,  # type: ignore[arg-type]
        )
        self.providers.append(provider)
        self.requests.append(requests)
        return provider, requests

    async def close(self) -> None:
        for provider in self.providers:
            await provider.close()


@pytest_asyncio.fixture
async def provider_factory() -> AsyncIterator[OfflineProviderFactory]:
    factory = OfflineProviderFactory()
    yield factory
    await factory.close()


@pytest.mark.asyncio
async def test_maps_text_response_and_all_metadata(
    provider_factory: OfflineProviderFactory,
) -> None:
    timestamps = iter([100.0, 100.25])
    provider, requests = provider_factory.build(
        [_response(_completion(), headers={"x-request-id": "request-123"})],
        clock=lambda: next(timestamps),
    )

    result = await provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
    )

    assert result.content == "hello"
    assert result.model_name == "response-model"
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 2
    assert result.usage.total_tokens == 5
    assert result.latency_ms == 250
    assert result.finish_reason is FinishReason.STOP
    assert result.provider_request_id == "request-123"
    assert result.tool_calls == []
    assert len(requests) == 1
    assert requests[0].url.path == "/compatible-mode/v1/chat/completions"
    request_body = json.loads(requests[0].content)
    assert request_body["model"] == FAKE_MODEL
    assert request_body["messages"] == [{"role": "user", "content": "hello"}]
    assert "tools" not in request_body
    assert request_body["enable_thinking"] is False
    assert request_body["stream"] is False


@pytest.mark.asyncio
async def test_multimodal_message_uses_one_non_streaming_mock_request(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(_completion())])
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this screenshot."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,ZmFrZS1pbWFnZQ==",
                        "detail": "high",
                    },
                },
            ],
        }
    ]
    original_messages = deepcopy(messages)

    await provider.chat(messages=messages, tools=None)

    assert messages == original_messages
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["messages"] == original_messages
    assert body["stream"] is False
    assert body["enable_thinking"] is False
    assert "tools" not in body


@pytest.mark.asyncio
async def test_multimodal_http_failure_has_zero_sdk_retries(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(status_code=503)])
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/webp;base64,ZmFrZQ==",
                        "detail": "high",
                    },
                },
            ],
        }
    ]

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=messages, tools=None)

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_ERROR
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_maps_multiple_function_tool_calls_in_order_and_preserves_json(
    provider_factory: OfflineProviderFactory,
) -> None:
    first_arguments = '{ "text": "first" }'
    second_arguments = '{"text":"second"}'
    provider, requests = provider_factory.build(
        [
            _response(
                _completion(
                    content=None,
                    finish_reason="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "echo", "arguments": first_arguments},
                        },
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {"name": "echo", "arguments": second_arguments},
                        },
                    ],
                )
            )
        ]
    )

    result = await provider.chat(
        messages=[{"role": "user", "content": "Use echo."}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "echo",
                    "description": "Echo input.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            }
        ],
    )

    assert [call.id for call in result.tool_calls] == ["call-1", "call-2"]
    assert [call.name for call in result.tool_calls] == ["echo", "echo"]
    assert [call.arguments for call in result.tool_calls] == [
        first_arguments,
        second_arguments,
    ]
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert len(requests) == 1
    request_body = json.loads(requests[0].content)
    assert request_body["model"] == FAKE_MODEL
    assert request_body["messages"] == [
        {"role": "user", "content": "Use echo."}
    ]
    assert request_body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo input.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    assert request_body["enable_thinking"] is False
    assert request_body["stream"] is False


@pytest.mark.parametrize(
    ("vendor_reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("vendor_specific_reason", FinishReason.UNKNOWN),
    ],
)
@pytest.mark.asyncio
async def test_maps_finish_reasons(
    provider_factory: OfflineProviderFactory,
    vendor_reason: str,
    expected: FinishReason,
) -> None:
    provider, _ = provider_factory.build(
        [_response(_completion(finish_reason=vendor_reason))]
    )

    result = await provider.chat(messages=[], tools=None)

    assert result.finish_reason is expected


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (None, (None, None, None)),
        ({"prompt_tokens": 4, "total_tokens": 4}, (4, None, 4)),
        (
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            (0, 0, 0),
        ),
    ],
)
@pytest.mark.asyncio
async def test_maps_missing_and_zero_usage(
    provider_factory: OfflineProviderFactory,
    usage: object,
    expected: tuple[int | None, int | None, int | None],
) -> None:
    provider, _ = provider_factory.build([_response(_completion(usage=usage))])

    result = await provider.chat(messages=[], tools=None)

    assert (
        result.usage.input_tokens,
        result.usage.output_tokens,
        result.usage.total_tokens,
    ) == expected


@pytest.mark.asyncio
async def test_missing_provider_request_id_maps_to_none(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, _ = provider_factory.build([_response(_completion())])

    result = await provider.chat(messages=[], tools=None)

    assert result.provider_request_id is None


@pytest.mark.asyncio
async def test_sdk_response_validation_failure_is_safely_classified(
    provider_factory: OfflineProviderFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _ = provider_factory.build([_response(_completion())])
    request = httpx.Request("POST", f"{FAKE_BASE_URL}/chat/completions")
    validation_error = APIResponseValidationError(
        httpx.Response(200, request=request),
        body={"raw": "fake-validation-secret"},
    )

    async def fail_validation(**kwargs: object) -> None:
        del kwargs
        raise validation_error

    monkeypatch.setattr(provider._client.chat.completions, "create", fail_validation)

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert "fake-validation-secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    "body",
    [
        {
            "id": "chatcmpl-empty",
            "object": "chat.completion",
            "created": 1,
            "model": "response-model",
            "choices": [],
        },
        _completion(model=""),
        _completion(content=["not", "text"]),
        _completion(finish_reason=""),
        _completion(
            finish_reason="tool_calls",
            content=None,
            tool_calls=[
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                }
            ],
        ),
        _completion(
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 99}
        ),
    ],
)
@pytest.mark.asyncio
async def test_invalid_response_shapes_are_safely_classified(
    provider_factory: OfflineProviderFactory,
    body: dict[str, object],
) -> None:
    provider, _ = provider_factory.build([_response(body)])

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_timeout_is_classified_without_sdk_retry(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build(
        [httpx.ReadTimeout("fake-sensitive-timeout")]
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.TIMEOUT
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [
        ("2.5", 2.5),
        ("0", 0.0),
        ("-1", None),
        ("nan", None),
        ("inf", None),
        ("tomorrow", None),
    ],
)
@pytest.mark.asyncio
async def test_rate_limit_and_retry_after_mapping(
    provider_factory: OfflineProviderFactory,
    retry_after: str,
    expected: float | None,
) -> None:
    provider, _ = provider_factory.build(
        [_response(status_code=429, headers={"retry-after": retry_after})]
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    error = exc_info.value
    assert error.code is ProviderErrorCode.RATE_LIMITED
    assert error.retry_after_seconds == expected


@pytest.mark.asyncio
async def test_authentication_failure_is_classified(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, _ = provider_factory.build([_response(status_code=401)])

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.AUTHENTICATION_FAILED


@pytest.mark.parametrize("outcome", [_response(status_code=400), _response(status_code=503)])
@pytest.mark.asyncio
async def test_other_http_failures_are_provider_errors(
    provider_factory: OfflineProviderFactory,
    outcome: httpx.Response,
) -> None:
    provider, requests = provider_factory.build([outcome])

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_ERROR
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_connection_failure_is_provider_error(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, _ = provider_factory.build(
        [httpx.ConnectError("fake-sensitive-connection-failure")]
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value.code is ProviderErrorCode.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_cancelled_error_propagates_unchanged(
    provider_factory: OfflineProviderFactory,
) -> None:
    cancellation = asyncio.CancelledError("cancel provider call")
    provider, _ = provider_factory.build([cancellation])

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await provider.chat(messages=[], tools=None)

    assert exc_info.value is cancellation


@pytest.mark.asyncio
async def test_request_messages_and_tools_are_not_modified(
    provider_factory: OfflineProviderFactory,
) -> None:
    messages = [{"role": "user", "content": {"parts": ["hello"]}}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo input.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            },
        }
    ]
    original_messages = deepcopy(messages)
    original_tools = deepcopy(tools)
    provider, _ = provider_factory.build([_response(_completion())])

    await provider.chat(messages=messages, tools=tools)

    assert messages == original_messages
    assert tools == original_tools


@pytest.mark.asyncio
async def test_repeated_calls_do_not_accumulate_request_state(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build(
        [
            _response(_completion(content="first")),
            _response(_completion(content="second")),
        ]
    )

    first = await provider.chat(
        messages=[{"role": "user", "content": "one"}],
        tools=None,
    )
    second = await provider.chat(
        messages=[{"role": "user", "content": "two"}],
        tools=None,
    )

    assert first.content == "first"
    assert second.content == "second"
    assert len(requests) == 2
    first_request = json.loads(requests[0].content)
    second_request = json.loads(requests[1].content)
    assert first_request["messages"] == [
        {"role": "user", "content": "one"}
    ]
    assert second_request["messages"] == [
        {"role": "user", "content": "two"}
    ]
    assert first_request["enable_thinking"] is False
    assert second_request["enable_thinking"] is False


@pytest.mark.asyncio
async def test_provider_errors_settings_and_logs_do_not_leak_secrets(
    provider_factory: OfflineProviderFactory,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    response_secret = "fake-raw-response-secret"
    authorization = f"Bearer {FAKE_API_KEY}"
    provider, _ = provider_factory.build(
        [
            _response(
                {"error": {"message": response_secret}},
                status_code=500,
            )
        ]
    )

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(
            messages=[{"role": "user", "content": "fake-private-request"}],
            tools=None,
        )

    error = exc_info.value
    captured = capsys.readouterr()
    public_values = [
        str(error),
        repr(error),
        json.dumps(error.to_public_dict(), sort_keys=True),
        repr(_settings()),
        caplog.text,
        captured.out,
        captured.err,
    ]
    for rendered in public_values:
        assert FAKE_API_KEY not in rendered
        assert authorization not in rendered
        assert response_secret not in rendered
        assert "fake-private-request" not in rendered


@pytest.mark.asyncio
async def test_existing_runner_and_registry_complete_real_adapter_tool_cycle_offline(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build(
        [
            _response(
                _completion(
                    content=None,
                    finish_reason="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-echo",
                            "type": "function",
                            "function": {
                                "name": "echo",
                                "arguments": '{"text":"deterministic"}',
                            },
                        }
                    ],
                )
            ),
            _response(_completion(content="The deterministic tool completed.")),
        ]
    )
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = await AgentRunner(provider, registry).run(
        [{"role": "user", "content": "Use the echo tool."}]
    )

    assert result.answer == "The deterministic tool completed."
    assert result.tools_used == ["echo"]
    assert len(requests) == 2
    request_bodies = [json.loads(request.content) for request in requests]
    assert [body["enable_thinking"] for body in request_bodies] == [False, False]
    second_messages = request_bodies[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert json.loads(second_messages[-1]["content"])["data"] == {
        "text": "deterministic"
    }
