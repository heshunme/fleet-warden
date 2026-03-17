# FleetWarden Backend

## Development

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
uv run fleetwarden-worker
```

From the repo root you can also start the full dev stack with:

```bash
./start-dev.sh
```

## Environment

Backend settings load from `backend/.env`.

Start from:

```bash
cp .env.example .env
```

Relevant variables:

- `FLEETWARDEN_DATABASE_URL`
- `FLEETWARDEN_SSH_CONFIG_PATH`
- `FLEETWARDEN_REMOTE_AGENT_COMMAND`
- `FLEETWARDEN_LLM_TASKSPEC_MODEL`
- `FLEETWARDEN_LLM_PROPOSAL_MODEL`
- `FLEETWARDEN_LLM_API_BASE`
- `FLEETWARDEN_LLM_API_KEY`

LiteLLM is only used for TaskSpec and proposal generation. If model config is missing or the call fails, the backend falls back to the built-in stub agents.

## Tests

```bash
uv run python -m pytest
```

Focused orchestration checks:

```bash
uv run python -m pytest tests/test_state_machine.py tests/test_state_machine_matrix.py tests/test_orchestrator.py
```

Review checklist:

- See [`docs/orchestrator_review_checklist.md`](../docs/orchestrator_review_checklist.md) before merging orchestration changes.
