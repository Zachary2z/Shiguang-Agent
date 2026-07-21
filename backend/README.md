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

## M0-1B OpenAI-compatible provider

`app.providers.OpenAICompatibleProvider` is the only real model adapter. It implements the
existing `nanobot_core.providers.ModelProvider` contract and uses the official `AsyncOpenAI`
Chat Completions client. The adapter is deliberately outside `nanobot_core`: the core still has
no SDK or network dependency and the existing `AgentRunner` and `ToolRegistry` remain the only
tool execution path.

The adapter sends non-streaming requests with SDK retries disabled, maps response model, Token
usage, monotonic latency, finish reason, official request ID, text, and ordered function tool
calls into the M0-1A contract. Function arguments remain the exact JSON string supplied by the
SDK; only the existing `ToolRegistry` parses and validates them. Provider exceptions are reduced
to the five stable, safe `ProviderErrorCode` values without logging raw requests, responses,
credentials, or Authorization headers.

The application can start and serve `/healthz` without model configuration. Only
`OpenAICompatibleProvider.from_settings()` requires all of:

- `MODEL_API_BASE`
- `MODEL_API_KEY`
- `MODEL_NAME`
- `MODEL_TIMEOUT_SECONDS`

`MODEL_API_KEY` is stored as `SecretStr`; timeout must be finite and positive. Copy the variable
names from `.env.example` into the ignored repository-root `.env` only when real verification is
authorized.

Default verification is fully offline:

```bash
python -m ruff check .
python -m mypy app migrations nanobot_core
python -m pytest -q -m "not real_provider"
python -m pytest -q tests/core
```

The real test is a separately marked, deterministic Tool Calling cycle with no file writes,
messages, or external tools. It remains skipped unless the environment switch is exact and all
four model settings are complete:

```bash
RUN_REAL_MODEL_TESTS=1 python -m pytest -q -m real_provider -rs
```

This authorizes one test case and at most two non-streaming Chat Completions requests. It must not
be run without explicit user approval. M0-1B has passed that separately authorized acceptance;
M0-1C development has no authorization to repeat it.

## M0-1C AgentRun and ToolRun

`nanobot_core.agent.AgentRunner` remains the only execution loop. Its optional synchronous
observer emits immutable provider-neutral events containing only model metadata, structural tool
summaries, safe identifiers, and argument fingerprints. Events never contain prompts, model
content, raw tool values, SDK types, database sessions, or application entities.

The same Runner now enforces three generic boundaries:

- at most eight executed Tool Calls per Run, counting every call in multi-call responses;
- a cancellable total deadline of at most 60 seconds using monotonic time;
- SHA-256 detection of the same tool with canonically equivalent JSON arguments.

The ninth call and a repeated call are recorded as blocked and are not executed. Active Provider
or Tool awaits are cancelled at the deadline. Caller cancellation is never swallowed.

The application owns `AgentRunStatus` and `ToolRunStatus`, `AgentRunService`, the single
`AgentRunRepository`, SQLAlchemy models, trace generation, aggregation, and pricing. The
`20260721_0002` migration creates only `agent_runs` and `tool_runs` directly on
`20260721_0001`; downgrade removes both and a second upgrade recreates them. SQLite foreign keys
are enabled on every application connection.

Model-call metadata is stored as a safe JSON summary on `agent_runs` because M0-1C allows only
two new tables. Stable query fields remain dedicated columns. Token values reuse the core
`TokenUsage` contract: `None` stays unknown and zero stays zero. Configured per-million input and
output prices use `Decimal`; missing tokens, missing rates, or a changed model produce an unknown
cost with a reason rather than zero.

`AgentRunService.get_by_trace_id()` requires both `user_id` and `trace_id`; its SQL filters both
fields and returns the same `None` result for a missing trace and another user's trace. Successful
lookups return the complete safe summary with ToolRuns ordered by sequence and explicit timeout,
tool-limit, repetition, and external-cancellation flags. No HTTP route, SSE stream, approval flow,
User/Session/Message table, or M0-2 feature is included.

## M0-2A collection domain

`app.domain.collections` owns the validated User, Session, Message, Source, CollectionItem,
CollectionSource, provider-neutral Place/Event kind, and collection status contracts. The shared
`app.domain.identifiers` and `app.domain.time` modules are the only application implementations
for opaque IDs and UTC normalization; the existing run-tracking code uses the same helpers.

`SqlAlchemyCollectionRepository` requires `user_id` on every public query and write. Message
ownership is resolved through Session. CollectionSource ownership is checked before a write and
is also enforced by composite SQLite foreign keys, so a Source and CollectionItem from different
users cannot be linked even through direct SQL. Missing and cross-user resources share the same
safe not-found behavior.

M0 sessions persist only `web` and `demo` channels. Persisted messages accept only `user` and
`assistant`; system prompts and raw tool payloads are rejected by both domain/repository and
database constraints, and message content is excluded from object representations. `failed`
and `recognizing` are separate recognition-workflow states represented by Source/AgentRun, never
CollectionItem statuses. A CollectionItem is created only for a real collection outcome such as
`active`, `pending_selection`, or `pending_details`; the domain model, repository writes and
migration check constraint enforce that invariant.

Revision `20260721_0003` creates only `users`, `sessions`, `messages`, `sources`,
`collection_items`, and `collection_sources` on top of `20260721_0002`. Revision
`20260721_0004` removes legacy transient collection rows and tightens the status constraint.
Downgrading to `20260721_0002` removes only those six tables and preserves AgentRun/ToolRun.
M0-2A includes no extractor, model invocation, auto-save, Undo token, HTTP collection route, POI
matching, or Demo initialization.
