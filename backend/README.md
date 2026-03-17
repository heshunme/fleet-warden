# FleetWarden Backend

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run fleetwarden-worker
```

From the repo root you can also start the full dev stack with:

```bash
./start-dev.sh
```

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
