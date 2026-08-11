# Model-Driven Planning Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Use `ponytail` throughout. Delete each superseded path in the same commit that replaces it.

**Goal:** Replace fixed one-hour/two-place deterministic plan selection with one model-driven proposal boundary while retaining the existing deterministic scheduler, map facts, versioning, confirmations, and execution services.

**Architecture:** Agent text and collection selection feed the same `PlanExperienceService`. The existing `ModelProvider` returns request-local candidate identities, order, visit durations, and either three initial proposals or one adjusted proposal. The existing `MapPlanFactResolver` fetches only routes used by those proposals. The existing `PlanDraftService` converts proposals to exact timelines and rejects hard conflicts. The existing `ExternalPlaceSupplementService` remains the only Amap supplement boundary. No second planner, scorer, parser, repository, workflow, provider, or state machine is allowed.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy/Alembic, existing Nanobot `ModelProvider`, existing Amap `MapProvider`, Next.js/React/TypeScript, pytest, Vitest/Testing Library, Playwright.

**Baseline:** `ff24176722fefab4d2dae0bb0280e040be04767d`

**Branch:** `codex/m1-model-driven-planning`

**Non-goals:** M2, multi-day/cross-city planning, recommendation ranking, vector search, external Event search, automatic retries, new dependencies, and real API calls during development.

---

## Task 1: Align the Product Contract Before Code

**Files:**
- Modify: `docs/product/拾光_PRD_v1.0.md`
- Modify: `docs/product/拾光_核心用户流程_v1.0.md`
- Modify: `docs/technical/拾光_MVP技术方案_v0.1.md`
- Modify: `docs/DEVELOPMENT_STAGES.md`
- Modify: `docs/DEV_STATUS.md`
- Reference: `docs/technical/M1_MODEL_DRIVEN_PLANNING_DESIGN.md`

- [ ] Replace “one core + at most one auxiliary” with “one main + two alternatives; model chooses items/order/duration”.
- [ ] State that Agent natural language is primary and collection selection is secondary; both share one workflow.
- [ ] State that deterministic code validates facts and hard constraints but does not choose the itinerary.
- [ ] Record selected collections as preferred by default and explicitly required only when marked required.
- [ ] Record external supplement and missing-origin behavior exactly as the design document specifies.
- [ ] Delete conflicting historical wording instead of adding compatibility notes beside it.
- [ ] Mark the corrective work “in progress”; keep M2-0 “not started”.

**Check:**

```bash
rg -n "最多一个辅助|固定.*60|每项.*一小时|一个核心" docs
git diff --check
```

Expected: no active product rule retains the old fixed planner.

**Commit:**

```bash
git add docs
git commit -m "docs: define model-driven planning"
```

## Task 2: Add One Strict Model Proposal Contract

**Files:**
- Modify: `backend/app/domain/plans/drafts.py`
- Create: `backend/app/application/plan_proposals.py`
- Modify: `backend/app/domain/plans/__init__.py`
- Create: `backend/tests/unit/test_plan_proposals.py`

- [ ] First write failing tests for:
  - exactly three initial proposals;
  - first proposal role `main`, the others `alternative`;
  - request-local candidate keys only;
  - positive model-suggested visit durations;
  - required candidates cannot be silently omitted;
  - duplicate proposal identity is rejected;
  - malformed JSON/tool calls/unknown identities map to the existing fixed planning error;
  - one model request and zero automatic retries.
- [ ] Add minimal strict contracts to the existing planning domain:

```python
class PlanProposalItem(PlanContract):
    candidate_key: str
    visit_duration_seconds: int = Field(gt=0, le=24 * 60 * 60)

class PlanOptionProposal(PlanContract):
    items: tuple[PlanProposalItem, ...] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)

class PlanProposalSet(PlanContract):
    options: tuple[PlanOptionProposal, ...] = Field(min_length=1, max_length=3)
```

- [ ] Implement one `PlanProposalService` using the existing `ModelProvider` and `structured_response_format`.
- [ ] Give the model only sanitized candidate facts, user constraints, preferences, selected/required markers, current Shanghai time, and opaque candidate keys.
- [ ] Do not expose database IDs where an opaque request-local key suffices.
- [ ] Do not let the model invent routes, price, opening hours, weather, coordinates, POIs, or candidates.
- [ ] Keep initial generation and adjustment as methods on this one service; do not create a second parser.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q tests/unit/test_plan_proposals.py
../.venv/bin/python -m ruff check app/application/plan_proposals.py app/domain/plans/drafts.py tests/unit/test_plan_proposals.py
../.venv/bin/python -m mypy app/application/plan_proposals.py app/domain/plans/drafts.py
```

**Commit:**

```bash
git add backend/app/domain/plans backend/app/application/plan_proposals.py backend/tests/unit/test_plan_proposals.py
git commit -m "feat: add one plan proposal boundary"
```

## Task 3: Make the Existing Scheduler Consume Proposals

**Files:**
- Modify: `backend/app/application/map_plan_facts.py`
- Modify: `backend/app/application/plan_drafts.py`
- Modify: `backend/app/domain/plans/drafts.py`
- Replace expectations in: `backend/tests/application/test_plan_drafts.py`
- Create: `backend/tests/application/test_map_plan_facts.py`

- [ ] First write failing tests proving:
  - a long window can contain more than two visits;
  - different suggested durations remain different after scheduling;
  - proposal order is preserved;
  - only proposal edges cause map route requests;
  - missing origin yields one unknown first leg, never `0m/0s`;
  - fixed Event windows and known routes are hard constraints;
  - invalid proposal A does not mutate B or C;
  - the scheduler never invents a replacement item.
- [ ] Remove `MAX_PLAN_FACT_CANDIDATES = 6` and `_VISIT_SECONDS = 60 * 60`.
- [ ] Remove `visit_duration_seconds` from pre-proposal candidate facts; duration comes from `PlanProposalItem`.
- [ ] Split the existing resolver flow without introducing another resolver:

```python
candidate_facts = await resolver.resolve_candidates(...)
proposals = await proposal_service.generate(..., candidate_facts=candidate_facts)
route_facts = await resolver.resolve_proposal_routes(..., proposals=proposals)
draft = draft_service.generate(..., proposals=proposals, route_facts=route_facts)
```

- [ ] Route only distinct origin/adjacent edges referenced by proposals; do not precompute all candidate pairs.
- [ ] Delete deterministic `_rank_key`, fixed primary/auxiliary selection, fixed two-item validation, and their reason codes if no remaining caller needs them.
- [ ] Preserve the existing `PlanDraftService` as the only exact scheduler and post-generation validator.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/application/test_plan_drafts.py \
  tests/application/test_map_plan_facts.py
../.venv/bin/python -m ruff check app/application/map_plan_facts.py app/application/plan_drafts.py app/domain/plans/drafts.py
../.venv/bin/python -m mypy app/application/map_plan_facts.py app/application/plan_drafts.py app/domain/plans/drafts.py
```

**Commit:**

```bash
git add backend/app/application/map_plan_facts.py backend/app/application/plan_drafts.py backend/app/domain/plans/drafts.py backend/tests/application
git commit -m "refactor: schedule model plan proposals"
```

## Task 4: Feed Amap Supplements Into the Same Proposal Boundary

**Files:**
- Modify: `backend/app/application/external_place_supplement.py`
- Modify: `backend/app/domain/plans/supplement.py`
- Modify: `backend/tests/application/test_external_place_supplement.py`
- Modify: `backend/tests/application/test_structured_collection_retrieval.py`

- [ ] Write failing tests for:
  - saved candidates satisfy the request: no external search;
  - saved restaurant is outside the explicit range: one restaurant gap may be searched;
  - `collection_only`: no external search;
  - no eligible collection core: approval before search;
  - external Event request: never searched;
  - external result is labeled `高德补充 · 未收藏` and remains uncollected after plan confirmation;
  - at most one search per explicit gap and zero automatic retries.
- [ ] Change `ExternalPlaceSupplementService` to return candidate facts/approval/recovery only; remove its call to `PlanDraftService`.
- [ ] Delete the old `len(selected) == 1 and constraints.include` trigger.
- [ ] Let `PlanProposalService` identify a semantic gap from the request and existing eligible candidates. The deterministic application boundary decides whether the gap may search automatically, needs approval, or is forbidden.
- [ ] After an allowed search, call the same proposal service once more with the added candidate; do not create fallback proposals in rules.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/application/test_external_place_supplement.py \
  tests/application/test_structured_collection_retrieval.py
```

**Commit:**

```bash
git add backend/app/application/external_place_supplement.py backend/app/domain/plans/supplement.py backend/tests/application
git commit -m "refactor: unify external place planning candidates"
```

## Task 5: Orchestrate Generation Through the Existing Worker

**Files:**
- Modify: `backend/app/application/plan_experience.py`
- Modify: `backend/app/worker/__main__.py`
- Modify: `backend/app/application/content_import_jobs.py`
- Modify: `backend/tests/contract/test_m1_5_plans.py`
- Modify: `backend/tests/contract/test_m1_agent_intent_routing.py`

- [ ] Write failing contract tests showing Agent text and collection selection reach the same executor and produce three initial options.
- [ ] Inject the single `PlanProposalService` beside existing services; do not add a new worker/job type.
- [ ] Generation order is: retrieve/hard-filter → optional authorized Amap supplement → model proposals → proposal routes → exact schedule → persist.
- [ ] Keep one model request normally; allow a second only when the first identifies an allowed external gap and Amap adds a candidate.
- [ ] Ensure cancellation, timeout, failure, idempotent replay, and AgentRun terminal state still use existing paths.
- [ ] Remove any remaining executor path that directly calls fixed deterministic proposal selection.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/contract/test_m1_5_plans.py \
  tests/contract/test_m1_agent_intent_routing.py \
  tests/contract/test_m1_3_content_import.py
```

**Commit:**

```bash
git add backend/app/application/plan_experience.py backend/app/application/content_import_jobs.py backend/app/worker/__main__.py backend/tests/contract
git commit -m "feat: generate plans from model proposals"
```

## Task 6: Preserve Selected and Required Collection Semantics

**Files:**
- Modify: `backend/app/domain/plans/contracts.py`
- Modify: `backend/app/application/agent_intents.py`
- Modify: `backend/app/schemas/api.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/application/structured_collection_retrieval.py`
- Modify: `frontend/components/collections-experience.tsx`
- Modify: `backend/tests/unit/test_plan_constraints.py`
- Modify: `backend/tests/application/test_structured_collection_retrieval.py`
- Modify: `frontend/tests/collections-experience.test.tsx`

- [ ] Add only one new contract field: `required_collection_item_ids`.
- [ ] Validate required IDs are a subset of selected IDs and preserve current count/ownership checks.
- [ ] Treat selected IDs as preferred inputs, not silent hard requirements.
- [ ] Treat required IDs as hard requirements; an impossible required item returns a conflict.
- [ ] Keep `collection_only` as the explicit switch that forbids unselected/external candidates.
- [ ] In the collection UI, add a native checkbox per selected item for “必须安排”; do not add a new selection framework.
- [ ] No database migration: constraints are already stored as JSON.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/unit/test_plan_constraints.py \
  tests/application/test_structured_collection_retrieval.py
cd ../frontend
npm test -- --run tests/collections-experience.test.tsx
```

**Commit:**

```bash
git add backend/app/domain/plans/contracts.py backend/app/application/agent_intents.py backend/app/schemas/api.py backend/app/api/router.py backend/app/application/structured_collection_retrieval.py backend/tests frontend/components/collections-experience.tsx frontend/tests/collections-experience.test.tsx
git commit -m "feat: distinguish preferred and required collections"
```

## Task 7: Confirm and Execute the Chosen Option

**Files:**
- Modify: `backend/app/domain/plans/drafts.py`
- Modify: `backend/app/domain/plans/experience.py`
- Modify: `backend/app/schemas/api.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/infrastructure/repositories/plans.py`
- Modify: `backend/app/application/plan_execution.py`
- Modify: `backend/app/application/plan_sharing.py`
- Modify: `backend/tests/contract/test_m1_5_plans.py`
- Modify: `backend/tests/contract/test_m1_6_execution.py`
- Modify: `backend/tests/contract/test_m1_7_sharing.py`

- [ ] Add `option_index` to `PlanConfirmRequest`; include it in the idempotency fingerprint.
- [ ] Add one JSON-backed `execution_option_index` to `PlanDraftResult`, defaulting to `0` for old stored drafts.
- [ ] At confirm, validate the index and persist it in existing `draft_json`; no database column or migration.
- [ ] Add one domain helper/property that returns the chosen option. Make calendar, navigation, feedback, and sharing use it instead of `options[0]` or `option_index == 0`.
- [ ] Confirming option 1 or 2 must execute/share that option and no other.
- [ ] A new draft must not supersede an older confirmed version until the new draft is explicitly confirmed.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/contract/test_m1_5_plans.py \
  tests/contract/test_m1_6_execution.py \
  tests/contract/test_m1_7_sharing.py
```

**Commit:**

```bash
git add backend/app/domain/plans backend/app/schemas/api.py backend/app/api/router.py backend/app/infrastructure/repositories/plans.py backend/app/application/plan_execution.py backend/app/application/plan_sharing.py backend/tests/contract
git commit -m "feat: execute the confirmed plan option"
```

## Task 8: Replace Constraint Replacement With Selected-Option Edits

**Files:**
- Modify: `backend/app/application/plan_proposals.py`
- Delete old parser code from: `backend/app/application/plan_adjustments.py`
- Modify: `backend/app/application/plan_experience.py`
- Modify: `backend/app/domain/jobs.py`
- Modify: `backend/app/schemas/api.py`
- Modify: `backend/app/api/router.py`
- Replace: `backend/tests/unit/test_plan_adjustments.py`
- Modify: `backend/tests/contract/test_m1_5_plans.py`

- [ ] First write failing tests for add, remove, replace, reorder, duration, time-window, pace, and range instructions.
- [ ] Add `base_option_index` to the adjustment request and existing job payload.
- [ ] Give `PlanProposalService.adjust` the selected base option, remaining candidates, known facts, current constraints, and instruction.
- [ ] Return one revised proposal plus a concise change summary and explicit constraint changes.
- [ ] Preserve all base items not touched by the returned actions.
- [ ] “再加一个公园” adds a park and keeps the previous itinerary.
- [ ] Adjustment produces one-option V2/V3, with JSON lineage (`source_plan_id`, `source_option_index`, `change_summary`) in `PlanDraftResult`; no migration.
- [ ] Delete `PlanAdjustmentParser`, `PlanAdjustmentPatch`, complete-list include/exclude replacement, and their old tests after the shared proposal boundary covers them.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/unit/test_plan_adjustments.py \
  tests/unit/test_plan_proposals.py \
  tests/contract/test_m1_5_plans.py
```

**Commit:**

```bash
git add -A backend/app/application/plan_adjustments.py backend/app/application/plan_proposals.py backend/app/application/plan_experience.py backend/app/domain/jobs.py backend/app/schemas/api.py backend/app/api/router.py backend/tests
git commit -m "fix: adjust the selected plan option"
```

## Task 9: Expose the Shared Experience in Agent and Plans UI

**Files:**
- Create: `frontend/components/plan-option-summary.tsx`
- Modify: `frontend/components/agent-experience.tsx`
- Modify: `frontend/components/plans-experience.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/tests/agent-experience.test.tsx`
- Modify: `frontend/tests/plans-experience.test.tsx`
- Modify: `frontend/tests/e2e/agent-import.spec.ts`
- Modify: `frontend/tests/e2e/plans.spec.ts`

- [ ] Extract only the visual option summary; do not duplicate plan state or API logic.
- [ ] Agent natural-language plan creation shows progress, then three compact option summaries and a link to full details.
- [ ] Plans page shows `1 主方案 + 2 备选`; each has “基于此方案调整” and “确认使用”.
- [ ] Adjustment and confirmation requests carry the visible selected option index.
- [ ] Adjusted versions show one option, source lineage, and change summary.
- [ ] Keep confirmed V2 visibly active while V3 is draft.
- [ ] Keep missing-origin draft usable but block confirmation/navigation with one clear prompt.

**Run:**

```bash
cd frontend
npm run lint
npm test -- --run \
  tests/agent-experience.test.tsx \
  tests/plans-experience.test.tsx
npx playwright test tests/e2e/agent-import.spec.ts tests/e2e/plans.spec.ts
```

**Commit:**

```bash
git add frontend
git commit -m "feat: expose model plan options and edits"
```

## Task 10: Final Offline Gate and Handoff

**Files:**
- Modify: `docs/DEV_STATUS.md`
- Modify: `docs/technical/M1_VALIDATION_REPORT.md`

- [ ] Search for deleted paths and duplicate services:

```bash
rg -n "MAX_PLAN_FACT_CANDIDATES|_VISIT_SECONDS|PlanAdjustmentParser|PlanAdjustmentPatch|options\[0\]|option_index == 0" backend/app
rg -n "class .*Plan.*Service|class .*Proposal|class .*Planner" backend/app
```

Expected: no active fixed planner/old parser; any option-0 compatibility is explicitly for old data only.

- [ ] Run the full offline gate:

```bash
cd backend
../.venv/bin/python -m pip check
../.venv/bin/python -m ruff check .
../.venv/bin/python -m mypy app migrations nanobot_core
APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 \
  ../.venv/bin/python -m pytest -q -m "not real_provider and not real_map_provider"
../.venv/bin/python -m alembic heads
cd ../frontend
npm run lint
npm test -- --run
npm run build
```

- [ ] Run the same focused backend suite with a `/tmp` socket-blocking pytest plugin.
- [ ] Record exact passed/skipped/deselected counts, net production lines, duplicate-rule review, and zero real API calls.
- [ ] Keep status “waiting real user QA”; do not close the repair from offline tests alone.

**Commit:**

```bash
git add docs/DEV_STATUS.md docs/technical/M1_VALIDATION_REPORT.md
git commit -m "docs: hand off model-driven planning QA"
```

## Task 11: Real User QA (Separate Explicit Authorization)

- [ ] Start from the exact candidate commit with a clean tree.
- [ ] Obtain explicit limits for real model and Amap calls.
- [ ] Test only the confirmed PRD paths:
  1. Agent natural-language long-window plan;
  2. one main + two alternatives;
  3. non-uniform durations and more than two visits where feasible;
  4. selected/required collections;
  5. authorized nearby restaurant supplement;
  6. missing-origin draft and later origin completion;
  7. adjust alternative with “再加一个公园”;
  8. confirm the chosen option and verify calendar/navigation/share use it.
- [ ] Zero automatic retries. Do not log secrets, model names, endpoints, request IDs, complete payloads, or responses.
- [ ] Only after real QA and no open P0/P1: ff-only integrate, update status, and push when separately authorized.
