"""OpenAI-compatible Chat Completions adapter for the configured model service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from copy import deepcopy
from math import isfinite
from typing import Any, cast

import httpx
from openai import (
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from app.config import ModelProviderSettings, Settings
from nanobot_core.providers import (
    FinishReason,
    Message,
    ModelProvider,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    StructuredOutput,
    StructuredOutputMode,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

_FINISH_REASONS = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
}
_OPENAI_SDK_LOGGER = logging.getLogger("openai._base_client")


class OpenAICompatibleProvider(ModelProvider):
    """Map one non-streaming SDK request into the provider-neutral contract."""

    def __init__(
        self,
        *,
        config: ModelProviderSettings,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # The SDK's DEBUG request-options entry includes messages when extra_body is set.
        _OPENAI_SDK_LOGGER.setLevel(max(_OPENAI_SDK_LOGGER.level, logging.INFO))
        self._client = AsyncOpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.api_base,
            timeout=config.timeout_seconds,
            max_retries=0,
            http_client=http_client,
        )
        self._model = config.model_name
        self._clock = clock

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> OpenAICompatibleProvider:
        """Construct the real adapter after deferred, secret-safe validation."""

        config = settings.require_model_provider()
        return cls(
            config=config,
            http_client=http_client,
            clock=clock,
        )

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_format: StructuredOutput | None = None,
    ) -> ModelResponse:
        if response_format is not None and not isinstance(
            response_format,
            StructuredOutput,
        ):
            raise TypeError("response_format must be StructuredOutput or None")
        if response_format is not None and tools is not None:
            raise ValueError("structured output cannot be combined with tools")
        request_messages = cast(
            list[ChatCompletionMessageParam],
            deepcopy(messages),
        )
        request_tools = cast(
            list[ChatCompletionToolParam] | None,
            deepcopy(tools),
        )
        request_response_format = self._map_response_format(response_format)
        started_at = self._clock()

        try:
            request: dict[str, Any] = {
                "model": self._model,
                "messages": request_messages,
                "extra_body": {"enable_thinking": False},
                "stream": False,
            }
            if request_tools is not None:
                request["tools"] = request_tools
            if request_response_format is not None:
                request["response_format"] = request_response_format
            completion = await self._client.chat.completions.create(**request)
        except asyncio.CancelledError:
            raise
        except APITimeoutError:
            raise ProviderError(code=ProviderErrorCode.TIMEOUT) from None
        except RateLimitError as exc:
            raise ProviderError(
                code=ProviderErrorCode.RATE_LIMITED,
                retry_after_seconds=self._retry_after(exc),
            ) from None
        except AuthenticationError:
            raise ProviderError(code=ProviderErrorCode.AUTHENTICATION_FAILED) from None
        except APIResponseValidationError:
            raise ProviderError(code=ProviderErrorCode.INVALID_RESPONSE) from None
        except APIStatusError as exc:
            if exc.status_code == 429:
                raise ProviderError(
                    code=ProviderErrorCode.RATE_LIMITED,
                    retry_after_seconds=self._retry_after(exc),
                ) from None
            if exc.status_code == 401:
                raise ProviderError(
                    code=ProviderErrorCode.AUTHENTICATION_FAILED
                ) from None
            raise ProviderError(code=ProviderErrorCode.PROVIDER_ERROR) from None
        except OpenAIError:
            raise ProviderError(code=ProviderErrorCode.PROVIDER_ERROR) from None

        latency_ms = max(0, int((self._clock() - started_at) * 1000))
        try:
            return self._map_response(completion, latency_ms=latency_ms)
        except (AttributeError, IndexError, TypeError, ValueError):
            raise ProviderError(code=ProviderErrorCode.INVALID_RESPONSE) from None

    @staticmethod
    def _map_response_format(
        response_format: StructuredOutput | None,
    ) -> dict[str, Any] | None:
        if response_format is None:
            return None
        if response_format.mode is StructuredOutputMode.JSON_OBJECT:
            return {"type": "json_object"}
        schema = response_format.schema_copy()
        assert schema is not None
        assert response_format.schema_name is not None
        return {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.schema_name,
                "strict": response_format.strict,
                "schema": schema,
            },
        }

    async def close(self) -> None:
        """Close the SDK client and its underlying HTTP resources."""

        await self._client.close()

    @staticmethod
    def _map_response(completion: ChatCompletion, *, latency_ms: int) -> ModelResponse:
        if not completion.choices:
            raise ValueError("missing choices")

        choice = completion.choices[0]
        message = choice.message
        if message.content is not None and not isinstance(message.content, str):
            raise ValueError("invalid message content")
        tool_calls: list[ToolCall] = []
        for sdk_call in message.tool_calls or []:
            if not isinstance(sdk_call, ChatCompletionMessageFunctionToolCall):
                raise ValueError("unsupported tool call")
            if (
                not sdk_call.id.strip()
                or not sdk_call.function.name.strip()
                or not isinstance(sdk_call.function.arguments, str)
            ):
                raise ValueError("invalid function tool call")
            tool_calls.append(
                ToolCall(
                    id=sdk_call.id,
                    name=sdk_call.function.name,
                    arguments=sdk_call.function.arguments,
                )
            )

        usage = completion.usage
        token_usage = TokenUsage(
            input_tokens=(
                None if usage is None else getattr(usage, "prompt_tokens", None)
            ),
            output_tokens=(
                None if usage is None else getattr(usage, "completion_tokens", None)
            ),
            total_tokens=(
                None if usage is None else getattr(usage, "total_tokens", None)
            ),
        )
        raw_finish_reason = choice.finish_reason
        if not isinstance(raw_finish_reason, str) or not raw_finish_reason.strip():
            raise ValueError("invalid finish reason")
        finish_reason = _FINISH_REASONS.get(
            raw_finish_reason,
            FinishReason.UNKNOWN,
        )
        return ModelResponse(
            model_name=completion.model,
            usage=token_usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            provider_request_id=completion._request_id,
            content=message.content,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _retry_after(exc: APIStatusError) -> float | None:
        raw_value = exc.response.headers.get("retry-after")
        if raw_value is None:
            return None
        try:
            value = float(raw_value)
        except ValueError:
            return None
        if not isfinite(value) or value < 0:
            return None
        return value
