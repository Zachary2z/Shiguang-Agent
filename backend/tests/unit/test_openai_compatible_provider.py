"""Offline contract tests for the application-layer model provider."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable, Sequence
from copy import deepcopy
from time import monotonic

import httpx
import pytest
import pytest_asyncio
from openai import APIResponseValidationError

from app.config import Settings
from app.providers import OpenAICompatibleProvider
from nanobot_core.agent import AgentRunner
from nanobot_core.providers import (
    FinishReason,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    StructuredOutputMode,
)
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
        timeout_seconds: float = 7,
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
            _settings(model_timeout_seconds=timeout_seconds),
            **kwargs,  # type: ignore[arg-type]
        )
        self.providers.append(provider)
        self.requests.append(requests)
        return provider, requests

    async def close(self) -> None:
        for provider in self.providers:
            await provider.close()


class _ActiveSlowResponseStream(httpx.AsyncByteStream):
    """Yield regular progress while the full response exceeds one request deadline."""

    def __init__(
        self,
        payload: bytes,
        *,
        release_chunk: asyncio.Event,
        chunk_size: int = 1,
    ) -> None:
        self._chunks = tuple(
            payload[index : index + chunk_size]
            for index in range(0, len(payload), chunk_size)
        )
        self._release_chunk = release_chunk
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.finished = asyncio.Event()
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.started.set()
        try:
            for chunk in self._chunks:
                await self._release_chunk.wait()
                self._release_chunk.clear()
                yield chunk
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.finished.set()

    async def aclose(self) -> None:
        self.closed = True


async def _keep_stream_active(
    stream: _ActiveSlowResponseStream,
    release_chunk: asyncio.Event,
    *,
    interval_seconds: float,
) -> None:
    await stream.started.wait()
    while not stream.finished.is_set():
        release_chunk.set()
        await asyncio.sleep(interval_seconds)


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
    assert "response_format" not in request_body
    assert request_body["enable_thinking"] is False
    assert request_body["stream"] is False


@pytest.mark.asyncio
async def test_response_after_fifteen_seconds_but_before_thirty_succeeds(
    provider_factory: OfflineProviderFactory,
) -> None:
    timestamps = iter([100.0, 116.0])
    provider, requests = provider_factory.build(
        [_response(_completion(content="completed before hard guardrail"))],
        clock=lambda: next(timestamps),
        timeout_seconds=30,
    )

    result = await provider.chat(messages=[], tools=None)

    assert result.content == "completed before hard guardrail"
    assert result.latency_ms == 16_000
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_maps_json_schema_response_format_with_isolated_schema(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(_completion(content='{"ok":true}'))])
    source_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    original_schema = deepcopy(source_schema)
    response_format = StructuredOutput(
        mode=StructuredOutputMode.JSON_SCHEMA,
        schema_name="result_contract",
        json_schema=source_schema,
        strict=True,
    )
    source_schema["properties"] = {}

    result = await provider.chat(
        messages=[{"role": "user", "content": "return an object"}],
        tools=None,
        response_format=response_format,
    )

    assert result.content == '{"ok":true}'
    body = json.loads(requests[0].content)
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "result_contract",
            "strict": True,
            "schema": original_schema,
        },
    }
    assert response_format.json_schema == original_schema
    assert "properties" not in repr(response_format)


@pytest.mark.asyncio
async def test_maps_json_object_response_format(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(_completion(content="{}"))])

    await provider.chat(
        messages=[{"role": "user", "content": "return an object"}],
        tools=None,
        response_format=StructuredOutput(mode=StructuredOutputMode.JSON_OBJECT),
    )

    body = json.loads(requests[0].content)
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_rejects_tools_with_structured_output_before_network(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(_completion())])

    with pytest.raises(ValueError, match="cannot be combined"):
        await provider.chat(
            messages=[],
            tools=[{"type": "function", "function": {"name": "echo"}}],
            response_format=StructuredOutput(mode=StructuredOutputMode.JSON_OBJECT),
        )

    assert requests == []


@pytest.mark.asyncio
async def test_structured_output_provider_failure_has_no_fallback_request(
    provider_factory: OfflineProviderFactory,
) -> None:
    provider, requests = provider_factory.build([_response(status_code=400)])

    with pytest.raises(ProviderError) as caught:
        await provider.chat(
            messages=[{"role": "user", "content": "return an object"}],
            tools=None,
            response_format=StructuredOutput(
                mode=StructuredOutputMode.JSON_SCHEMA,
                schema_name="result",
                json_schema={"type": "object"},
            ),
        )

    assert caught.value.code is ProviderErrorCode.PROVIDER_ERROR
    assert len(requests) == 1


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


@pytest.mark.asyncio
async def test_total_wall_clock_deadline_cancels_continuously_active_sdk_request(
    provider_factory: OfflineProviderFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response_secret = "fake-timeout-response-secret"
    request_id = "fake-timeout-request-id"
    prompt_secret = "fake-timeout-prompt-secret"
    base64_secret = "data:image/png;base64,ZmFrZS10aW1lb3V0LWltYWdl"
    release_chunk = asyncio.Event()
    payload = json.dumps(_completion(content=response_secret)).encode()
    stream = _ActiveSlowResponseStream(payload, release_chunk=release_chunk)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "x-request-id": request_id,
            },
            stream=stream,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider.from_settings(
        _settings(model_timeout_seconds=0.03),
        http_client=http_client,
    )
    provider_factory.providers.append(provider)
    provider_factory.requests.append(requests)

    activity = asyncio.create_task(
        _keep_stream_active(
            stream,
            release_chunk,
            interval_seconds=0.005,
        )
    )
    started_at = monotonic()
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as exc_info:
            await provider.chat(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_secret},
                            {
                                "type": "image_url",
                                "image_url": {"url": base64_secret},
                            },
                        ],
                    }
                ],
                tools=None,
            )
    finally:
        await activity

    await provider.close()

    assert exc_info.value.code is ProviderErrorCode.TIMEOUT
    assert monotonic() - started_at < 0.5
    assert len(requests) == 1
    assert stream.cancelled.is_set()
    assert stream.finished.is_set()
    assert stream.closed is True
    assert activity.done()
    assert http_client.is_closed is True
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    public = (
        f"{exc_info.value!s}{exc_info.value!r}"
        f"{exc_info.value.to_public_dict()!r}{provider!r}{caplog.text}"
    )
    for secret in (
        response_secret,
        request_id,
        prompt_secret,
        base64_secret,
        FAKE_API_KEY,
        FAKE_BASE_URL,
        "Authorization",
    ):
        assert secret not in public


@pytest.mark.asyncio
async def test_segmented_sdk_response_completes_before_total_wall_clock_deadline(
    provider_factory: OfflineProviderFactory,
) -> None:
    release_chunk = asyncio.Event()
    stream = _ActiveSlowResponseStream(
        json.dumps(_completion(content="completed in time")).encode(),
        release_chunk=release_chunk,
        chunk_size=100,
    )
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=stream,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider.from_settings(
        _settings(model_timeout_seconds=0.2),
        http_client=http_client,
    )
    provider_factory.providers.append(provider)
    provider_factory.requests.append(requests)
    activity = asyncio.create_task(
        _keep_stream_active(
            stream,
            release_chunk,
            interval_seconds=0.005,
        )
    )

    result = await provider.chat(messages=[], tools=None)
    await activity

    assert result.content == "completed in time"
    assert len(requests) == 1
    assert stream.cancelled.is_set() is False
    assert stream.finished.is_set()


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
