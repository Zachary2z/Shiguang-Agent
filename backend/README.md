# Shiguang backend

M0-0B FastAPI infrastructure scaffold plus the business-neutral Nanobot core. Development
commands are documented in the repository root `README.md`.

## M0-1A Provider contract

`nanobot_core.providers.ModelResponse` requires `model_name`, `usage`, `latency_ms`, and a
provider-neutral `finish_reason`. `provider_request_id` is optional: `None` means the provider
did not supply one, while blank IDs are invalid. Existing `content` and `tool_calls` fields remain
part of the response.

`TokenUsage` always exists on a response, while each of `input_tokens`, `output_tokens`, and
`total_tokens` may be `None` when the provider does not report it. Zero is valid and negative or
boolean counts are invalid. When both component counts are known, a missing total is derived;
an explicit total must equal their sum. With only one known component, an explicit total cannot
be smaller than that component.

Providers normalize completion reasons to `stop`, `tool_calls`, `length`, `content_filter`, or
`unknown`. Raw vendor reason strings do not enter the public contract. A response containing
tool calls must use `tool_calls`, and that reason requires at least one call.

`ProviderError` exposes one of five stable codes and a fixed safe summary:

| Code | Retryable | Retry-after |
|---|---:|---|
| `PROVIDER_TIMEOUT` | yes | no |
| `PROVIDER_RATE_LIMITED` | yes | optional |
| `PROVIDER_AUTHENTICATION_FAILED` | no | no |
| `PROVIDER_INVALID_RESPONSE` | no | no |
| `PROVIDER_ERROR` | no | no |

`to_public_dict()` contains only the code, fixed summary, retry flag, and optional retry-after.
Provider SDK exceptions and raw response bodies may remain in the internal exception chain but
are never included in this public representation. The core does not retry automatically and does
not catch `asyncio` cancellation. M0-1A contains no real provider adapter, SDK, model configuration,
network call, persistence, or database migration.
