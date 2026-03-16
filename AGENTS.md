# FleetWarden Agent Guide

This repository is an early V1 implementation of FleetWarden: an SSH-first AI operations control plane with a Python backend, a React frontend, and a background worker.

This document is for future coding agents and collaborators. It focuses on the current project shape, the commands that actually work here, and the pitfalls already discovered during V1 bring-up.

## Repo Layout

- `backend/`
  Python backend managed with `uv`
- `frontend/`
  React + TypeScript + Vite frontend managed with `npm`
- `docs/PRD_v1.md`
  Product and architecture source of truth for V1 scope
- `start-dev.sh`
  Starts API, worker, and frontend dev server together

## Current Stack

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- AsyncSSH
- SQLite by default
- `uv` for dependency and script management

### Frontend

- React
- TypeScript
- Vite

## Development Commands

### Full stack

Run from repo root:

```bash
./start-dev.sh
```

This starts:

- API: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Worker: background task loop in `backend`

### Backend

Run from `backend/`:

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run fleetwarden-worker
```

### Frontend

Run from `frontend/`:

```bash
npm install
npm run dev
npm run build
```

## Testing

Run backend tests from `backend/`:

```bash
uv run python -m pytest
```

If `uv run pytest` behaves oddly in a constrained shell, prefer `uv run python -m pytest`.

### Important test isolation rule

Do not point tests at the repo-root SQLite database.

The backend test fixture intentionally reconfigures SQLAlchemy to use a per-test temporary SQLite file:

- `backend/tests/conftest.py`
- `backend/app/database.py`

This exists because using the shared root database caused WAL / file locking / disk I/O issues when tests and local services touched the same DB.

## Database Rules

### Runtime DB initialization must stay in app startup, not import time

Keep database initialization in FastAPI lifespan startup, not at module import time.

Reason:

- import-time `init_db()` broke tests because `TestClient` imports `app.main` before test fixtures can redirect the database
- startup-time initialization keeps app boot correct while still allowing tests to swap DBs safely

Relevant file:

- `backend/app/main.py`

### Database engine is reconfigurable on purpose

`backend/app/database.py` supports `configure_database(...)` and `get_engine()` so tests can switch to a temporary DB without patching the whole app.

Do not simplify this back to a single fixed global engine bound once at import time unless you also redesign test isolation.

## State Machine / Orchestrator Rules

The most fragile logic in this repo is in:

- `backend/app/orchestrator/service.py`

Be careful when changing task pause/resume or proposal approval behavior.

### Rule 1: resuming a paused task must preserve live pending proposals

If a node was paused while it already had a pending proposal, resuming the task must restore that node to `awaiting_approval`, not `awaiting_proposal`.

Reason:

- otherwise the worker generates a second proposal for the same node/round
- this creates duplicate or stale approval records

Current protection:

- `_resume_status_for_task_node(...)`

### Rule 2: paused proposals must stop being pending

When `pause-node` is used from the approval queue:

- the `TaskNode` becomes `paused`
- the `Proposal` must no longer stay `pending`
- the `Round` should no longer look actively actionable

Current behavior:

- proposal status becomes `paused`
- round status becomes `aborted`

### Rule 3: pending proposal queries must be defensive

`list_pending_proposals()` intentionally filters by both:

- `Proposal.status == "pending"`
- `TaskNode.status == "awaiting_approval"`

Keep that guard. It prevents stale proposals from reappearing in the approval queue if node state and proposal state drift.

## Worker Notes

The worker loop lives in:

- `backend/app/worker.py`

It currently:

- recovers `executing` nodes into `blocked` on startup
- polls for `awaiting_proposal` nodes
- generates one proposal per waiting node

If you change worker behavior, keep these constraints in mind:

- task progress must be idempotent enough to survive restarts
- proposals must not be regenerated for nodes that already have a pending approval

## SSH Discovery Notes

SSH node discovery is in:

- `backend/app/infra/ssh_config.py`

Supported V1 cases:

- `Host`
- `HostName`
- `User`
- `Port`
- `Include`
- `Host *` defaults

Keep tests updated if you change parsing behavior:

- `backend/tests/test_ssh_config.py`

One subtle point already fixed here:

- `Include` inside a default block must still preserve the already-collected default values

## Frontend Notes

The frontend is currently a single control-plane dashboard split into sections rather than a router-driven multi-page app.

Main entry points:

- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`

If you add environment variables for the frontend API base URL, keep:

- `frontend/src/vite-env.d.ts`

Without it, `import.meta.env` typing will break the TypeScript build.

## Git Workflow

Use `git` regularly during changes:

- `git status --short`
- `git diff --stat`
- targeted `git diff -- <path>`

This repo started from an almost empty baseline, so it is easy to accidentally broaden the change set.

## File Hygiene

Ignore and do not commit runtime noise:

- SQLite runtime artifacts like `*.db-shm` and `*.db-wal`
- virtualenv contents
- frontend build output unless explicitly asked

Current ignore rules live in:

- `.gitignore`

## Recommended Change Strategy

When touching backend orchestration code:

1. Read `docs/PRD_v1.md`
2. Read `backend/app/orchestrator/service.py`
3. Read the matching tests in `backend/tests/`
4. Make the change
5. Add or update a regression test
6. Run backend tests from `backend/`

When touching frontend behavior:

1. Update the UI section in `frontend/src/`
2. Run `npm run build`
3. Confirm API shapes still match `backend/app/api/schemas.py`

## Known Reality Of This Repo

- The agent logic is currently deterministic stub logic, not a real LLM integration yet
- Executors return usable structures, but remote execution behavior is still MVP-grade
- SQLite is fine for local development, but many race and lifecycle issues show up first in pause/resume and worker recovery paths

If something feels “surprisingly stateful,” assume the orchestrator and approval queue are the first place to inspect.

