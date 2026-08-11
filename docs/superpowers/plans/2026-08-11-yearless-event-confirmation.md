# Yearless Event Confirmation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and `ponytail`. This is independent of model-driven planning and must be a separate commit.

**Goal:** Preserve explicit month/day clues from screenshots or text without inventing a year.

**Architecture:** Reuse the existing Event clue fields and existing collection confirmation form. At the extraction trust boundary, reject structured dates whose year is absent from the source and keep the original month/day clue. The user supplies the year through the current native date inputs. No new parser, date library, database field, or migration.

**Baseline:** the implementation branch's latest main-compatible commit.

## Task 1: Prove the Trust-Boundary Failure

**Files:**
- Modify: `backend/tests/unit/test_text_extraction_contracts.py`
- Modify: `backend/tests/unit/test_image_recognition_service.py`
- Create: `backend/tests/application/test_extraction_output.py`

- [ ] Add fixed, synthetic model outputs for source text `7/1–8/28` with a guessed structured year.
- [ ] Assert final candidate has `event_start_date=None`, `event_end_date=None`, preserved month/day clues, and year uncertainty.
- [ ] Assert an explicitly sourced `2026/7/1–2026/8/28` remains structured.

**Run:**

```bash
cd backend
../.venv/bin/python -m pytest -q \
  tests/unit/test_text_extraction_contracts.py \
  tests/unit/test_image_recognition_service.py \
  tests/application/test_extraction_output.py
```

## Task 2: Fix the Existing Extraction Boundary

**Files:**
- Modify: `backend/app/application/extraction_output.py`
- Modify only if necessary: `backend/app/domain/collections/writes.py`

- [ ] At the one existing normalized extraction boundary, compare structured Event years with explicit source evidence already passed to that boundary.
- [ ] If no year is explicit, clear both structured dates and keep the original clues; do not substitute current year or publication year.
- [ ] If a year is explicit, preserve current behavior.
- [ ] Do not add keyword lists, a second date parser, OCR, fallback, repair call, or retry.

**Run:** repeat Task 1 tests, then Ruff and mypy for touched files.

**Commit:**

```bash
git add backend/app/application/extraction_output.py backend/app/domain/collections/writes.py backend/tests
git commit -m "fix: require explicit event year evidence"
```

## Task 3: Reuse the Existing Confirmation UI

**Files:**
- Modify: `frontend/components/collections-experience.tsx`
- Modify: `frontend/tests/collections-experience.test.tsx`

- [ ] Show `识别到 7 月 1 日至 8 月 28 日，年份待确认` from the existing clue fields.
- [ ] Leave existing native start/end date inputs empty.
- [ ] After the user chooses dates, reuse the current save/validation API; do not add a year-specific endpoint or picker.

**Run:**

```bash
cd frontend
npm test -- --run tests/collections-experience.test.tsx
npm run lint
```

**Commit:**

```bash
git add frontend/components/collections-experience.tsx frontend/tests/collections-experience.test.tsx
git commit -m "fix: ask for missing event year"
```

## Task 4: Offline Gate

```bash
cd backend
../.venv/bin/python -m ruff check .
../.venv/bin/python -m mypy app migrations nanobot_core
APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 \
  ../.venv/bin/python -m pytest -q -m "not real_provider and not real_map_provider"
cd ../frontend
npm test -- --run
npm run build
git diff --check
```

- [ ] Update `docs/DEV_STATUS.md` as “waiting real screenshot QA”.
- [ ] Do not run a real screenshot or model call without separate authorization.
