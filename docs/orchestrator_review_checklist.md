# Orchestrator Review Checklist

Use this checklist whenever a change touches FleetWarden orchestration, approvals, worker recovery, or SSH discovery behavior.

## Required checks

- The change routes state validation through `backend/app/domain/state_machine.py` instead of adding ad hoc guards in service code.
- Task actions (`approve_taskspec`, `reject_taskspec`, `pause`, `resume`, `cancel`) do not introduce a new status transition without a matching state-machine test.
- Proposal actions (`approve`, `reject`, `pause-node`) reject stale or non-actionable requests.
- Worker flows (`process_waiting_nodes`, `recover_executing_nodes`) still obey the same guards as API-triggered flows.
- Audit records still point at the correct entity type and entity id.
- Repeated requests and terminal-state requests are covered by tests.

## Minimum test run

```bash
uv run python -m pytest tests/test_state_machine.py tests/test_state_machine_matrix.py tests/test_orchestrator.py
```

For full verification:

```bash
uv run python -m pytest
```
