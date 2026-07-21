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
`collection_items`, and `collection_sources` on top of `20260721_0002`, with the final
CollectionItem status constraint applied directly in that single unpublished revision.
Downgrading to `20260721_0002` removes only those six tables and preserves AgentRun/ToolRun.
M0-2A includes no extractor, model invocation, auto-save, Undo token, HTTP collection route, POI
matching, or Demo initialization.

## M0-2B/C extraction and reversible writes

The single `TextExtractionService` returns strict provider-neutral Place/Event candidates and
performs at most one structural repair. `CollectionWriteService` consumes only candidate
outcomes and uses the existing `SqlAlchemyCollectionRepository` in one transaction to create or
reuse a Source, create all CollectionItems and CollectionSource links, persist one idempotency
operation, and associate every newly created item with one Undo group.

Revision `20260721_0005` extends the existing CollectionItem with business district, landmark,
metro, Event time clues, missing fields, and uncertainties. It adds
`collection_write_operations` and `collection_write_operation_items`; unique database constraints
cover `(user_id, idempotency_key)`, `(user_id, source_id)`, the Undo token hash, and operation
sequence. Composite foreign keys preserve user ownership. A downgrade to `0004` is allowed only
when those operation tables are empty and no new candidate metadata would be lost.

Undo tokens use cryptographically secure randomness, are returned only on the creating call,
expire after ten minutes by default, and are stored only as SHA-256 hashes. Replays return the
original ordered items without a second plaintext token. Patch and delete calls require an
explicit `user_id`; patches also require `expected_version`, increment only on a real change,
and expose only allowlisted fields. Logical deletion immediately removes items from default
queries while leaving Source and historical links intact. Undo uses a database compare-and-set
claim in the same transaction as group deletion; concurrent repeated Undo and DELETE requests
remain idempotent, while a stale DELETE after a real edit still reports a version conflict. This
phase adds no HTTP routes, real provider calls, POI matching, formal city code, or planning
behavior.

## M0-2D synchronous API

`app.api` exposes the M0-only `/api/v1` surface for Demo Session creation, plain-text message
submission, safe AgentRun lookup, collection list/detail, patch, logical delete, and path-bound
Undo. Route code only resolves the fixed server Demo identity, validates strict Pydantic input,
maps status codes, and serializes allowlisted responses. `CollectionQueryService` owns stable
filtering/pagination, while `TextCollectionWorkflow` is the only new orchestration entry point
and delegates extraction, writes, run tracking, and ownership checks to the existing services.

Message submission is synchronous and never claims to be queued after the request completes.
It requires a safe `idempotency_key`; deterministic Message/Source/trace identifiers plus the
existing database constraints prevent duplicate messages, sources, collections, links, and Undo
operations. A replay returns the same IDs and never returns the plaintext Undo Token again. The
application does not construct a real Provider from environment settings: tests inject the
offline Fake, while an app without an injected Provider still serves health, OpenAPI, and Demo
Session creation and returns `503 PROVIDER_NOT_CONFIGURED` only for text submission.

Public run responses omit user IDs, internal row IDs, tool-call IDs, argument fingerprints,
prompts, message content, and model response content. Collection detail exposes only Source ID,
type, parse status, and creation time. Request-validation handlers omit rejected values, so an
invalid message, Authorization/Cookie header, or Undo Token is not reflected in the response or
request log. No M0-2D migration or new environment variable is required.

Run the focused contract suite with:

```bash
python -m pytest -q tests/contract/test_m0_2d_api.py
```
