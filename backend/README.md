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

## M0-3C Place matching

`app.domain.places.matching` owns the one pure scoring policy, explainable evidence contracts,
four match outcomes, deterministic sorting, and explicit user-selection contract.
`app.application.PlaceMatchingService` owns the one orchestration path and injects the existing
`MapProvider`; it has no database, file, message, model, or HTTP implementation. Every call
carries its own `CityScope`, Event candidates are rejected before search, and at most three
GCJ-02 POIs are returned. Server thresholds come only from `Settings.place_matching_policy()`.
The unique, candidate, and minimum-gap thresholds must each be finite positive values in
`(0, 100]`; candidate score cannot exceed unique score. Public candidates meet the candidate
threshold and have no hard conflict, while an empty reliable set is represented as
`needs_context` when the provider returned POIs.

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

## M0-3A MapProvider Stub

`app.domain.places` owns the only provider-neutral POI, coordinate, route, weather, and
navigation DTOs. They are strict, extra-forbid, immutable Pydantic models with explicit stable
city codes, a restricted `PoiProvider` identity, and coordinate systems. Distances use
non-negative meters, durations use non-negative seconds, weather uses calendar dates and bounded Celsius values, and no DTO can
retain provider field names, credentials, headers, or raw responses.

`app.providers.MapProvider` owns the five asynchronous operations: `search_poi`, `get_poi`,
`route`, `weather`, and `build_navigation_uri`. Every operation accepts a request object with an
explicit `CityScope`; there is no global or mutable current city. `StubMapProvider` implements
that exact interface using constructor-injected immutable mappings. It performs no network,
environment, SDK, retry, cache, backoff, or persistence work and never consumes an ordered
response queue.

The shared `tests.fixtures.maps` module provides Shenzhen and Guangzhou fixtures for unique,
multiple, empty, timeout, detail, route, weather, and navigation outcomes. The Stub fixtures
explicitly simulate Amap-origin data, so each POI carries `provider=amap` and
can be stably identified by `provider + poi_id` without adding a second POI contract.

Focused verification:

```bash
python -m pytest -q tests/unit/test_place_contracts.py tests/contract/test_map_provider_contract.py tests/integration/test_map_provider_stub.py
```

M0-3A adds no configuration, dependency, database model, or Alembic revision. The real Amap
adapter, provider-field mapping, matching scores, candidate limits, formal POI persistence, and
branch-selection behavior remain explicitly outside this phase.

## M0-3B Amap Web Service adapter

`app.providers.AmapMapProvider` is the only production Amap adapter and directly implements the
existing `MapProvider`. One internal city mapping supplies both Amap adcodes and citycodes for
Shenzhen and Guangzhou; every method reads the explicit request `CityScope`, with no process-wide
city setting. Search uses `citylimit=true`, detail validates POI ID and city ownership, all four
route modes return only GCJ-02 endpoints plus total meters/seconds, forecast weather maps dates
and bounded Celsius values, and the Amap marker URI is built locally without a key. Search and
detail POIs always preserve the restricted `provider=amap`, provider-local `poi_id`, formal
`city_code`, and GCJ-02 coordinate system.

The HTTP origin is fixed to `https://restapi.amap.com`. A trailing slash is normalized; every
other hostname, suffix-confusion hostname, userinfo, non-HTTPS scheme, explicit port, path,
query, fragment, control character, or malformed URL fails before provider construction. Vendor
and parsing exceptions are caught internally and a new fixed `MapProviderError` is raised only
after leaving the `except` block, so public errors have no context/cause and retain no HTTP
request, response, URL, key, raw body, or vendor field.

Infocodes `10012/10013` are non-retryable authentication/permission failures;
`10014/10015/10019` are bounded rate-limit failures; `10016/10017` and `3xxxx` are bounded
temporary-unavailability failures. Unknown infocodes remain invalid responses and Amap `info`
text is never published.

`create_amap_http_client()` is the only HTTP client constructor and accepts an injected
`MockTransport`. The provider owns and closes the client. One logical call makes at most two HTTP
attempts. Timeout, connection, HTTP 429, selected 5xx, and explicit Amap throttling/engine errors
may retry; authentication, invalid input/response, empty results, and other 4xx do not. Numeric
`Retry-After` is capped, the wait function is injectable, cancellation propagates, and public
errors contain only stable codes and summaries.

Offline focus suite:

```bash
python -m pytest -q tests/unit/test_amap_provider.py tests/test_config.py
```

The separately authorized real marker performs five read-only logical HTTP calls, with at most
ten attempts at the default retry ceiling, plus a network-free marker URI build:

```bash
RUN_REAL_MAP_TESTS=1 python -m pytest -q -m real_map_provider -rs
```

It remains skipped unless both the exact switch and complete Amap settings are present. Do not
run it without a new user authorization. M0-3B does not implement matching scores, candidate
limits/selection, POI persistence, or exact/any-branch behavior.

## M0-4A private file storage

`app.providers.StorageProvider` is the only provider-neutral file boundary. It streams private
writes, returns lifecycle metadata, exposes an application-route-required access descriptor,
and deletes valid missing keys idempotently. Public DTOs and errors never contain file bytes,
original filenames, absolute paths, temporary names, or a fabricated local/public URL.

`app.infrastructure.storage.LocalPrivateStorageProvider` is the only local adapter. It writes
under the injected `STORAGE_PRIVATE_ROOT` with `0700` directories and `0600` files, uses
`secrets.token_urlsafe` opaque keys, reserves keys exclusively, and publishes completed data and
metadata without overwriting an existing object. Size is enforced while consuming the async
stream; empty data, disallowed MIME types, and mismatched PNG/JPEG/WebP signatures are rejected.
Failure and `CancelledError` paths clean reservations, temporary files, and any partially
published object, while cancellation itself propagates unchanged.

The local access contract intentionally returns
`application_download_route_required` because M0-4A has no authenticated download route. It
never emits `file://`, an absolute path, or a fake HTTP URL. `Source.file_key` remains the only
source pointer; there is no File/Attachment/Blob table or repository and no migration or new
dependency.

Offline focus suite:

```bash
python -m pytest -q tests/contract/test_storage_provider_contract.py tests/integration/test_local_private_storage.py tests/test_config.py
```

## M0-4B safe web parsing

`app.providers.WebContentProvider` is the only provider-neutral public web boundary. Its strict
contracts live in `app.domain.web` and return either bounded page content or a stable recoverable
failure. Success contains normalized and final URLs, title, cleaned text, allowlisted metadata,
content type, UTC fetch time, and safe diagnostics. Failure contains no source URL, response body,
credentials, DNS details, exception text, or traceback, and advertises future supply-text and
send-screenshot recovery actions without implementing those workflows.

`HttpxWebContentProvider` receives an explicit `AsyncClient` and resolver. The single URL/SSRF
policy permits only HTTP(S) on ports 80/443, rejects userinfo, ambiguous IP spellings, localhost,
metadata targets, and every non-global resolved address, and rejects mixed public/private DNS
answers. Before every request and redirect it resolves and validates again, then connects to the
validated IP while retaining the logical Host header and TLS SNI. Redirects are explicit, capped
at five, and loop-checked. Environment proxies, authentication, cookies, automatic redirects,
automatic retries, and keepalive reuse are disabled; cancellation propagates.

Only HTML, XHTML, and plain text are accepted. Wire and decompressed bodies are limited to 2 MB,
cleaned text to 50,000 characters, and title/metadata fields to contract-specific limits. One
BeautifulSoup extractor removes scripts, styles, navigation, and hidden content and exposes only
description, canonical, and the title/description/site-name Open Graph allowlist. BeautifulSoup is
the only dependency added because the standard library has no maintained tolerant HTML tree parser
and maintaining a second extractor is forbidden. There are no new settings, routes, persistence,
migrations, screenshot/OCR handling, or unified input workflow.

Offline focus suite:

```bash
python -m pytest -q tests/contract/test_web_content_provider_contract.py tests/unit/test_web_url_security.py tests/unit/test_httpx_web_content_provider.py
```

## M0-4C private screenshot recognition

`app.application.image_recognition.ImageRecognitionService` is the sole screenshot application
service. It accepts a bounded async stream, reuses the configured storage MIME/signature/size
policy, validates the complete JPEG/PNG/WebP decode before any storage or model call, then writes
through the existing `StorageProvider` with `ORIGINAL_SCREENSHOT` retention. Pillow is the only
new image dependency: Python's standard library has no complete JPEG/PNG/WebP decoder and cannot
reliably detect truncation, damaged images, decompression bombs, dimensions, or pixel counts.
Validation rejects animated images, dimensions over 12,000 pixels per side, and images over 40
million pixels. EXIF location is never read or promoted to location evidence.

Recognition uses the existing provider-neutral `Message` dictionary with text and `image_url`
content parts. `OpenAICompatibleProvider` continues to send one non-streaming SDK request per
`chat()` call with `max_retries=0`; offline MockTransport tests cover the serialized multimodal
body and zero SDK retry behavior. Text and image services share `extraction_output` for response
length checks, tool-call rejection, safe validation issues, and the sole structural repair.

The service returns a tuple of existing `PrivateFileMetadata` and `ExtractionResult`; it does not
define `ImageCandidate`, `OcrCandidate`, a second response DTO, a second model provider, or a
vision runner. Present screenshot price and location clues are rebuilt with explicit
`Uncertainty`; formal POI, coordinates, city code, and screenshot-only opening hours are absent
from the candidate schema. Provider error, unexpected exception, and cancellation paths delete
only the object created by that call. There is no HTTP upload route, Source/Collection workflow,
new setting, migration, real vision marker, or M0-4D unified input pipeline.

Offline focus suite:

```bash
python -m pytest -q tests/unit/test_image_recognition_service.py tests/unit/test_openai_compatible_provider.py tests/unit/test_text_extraction_service.py
```
