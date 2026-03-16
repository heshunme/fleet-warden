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
uv run pytest
```
