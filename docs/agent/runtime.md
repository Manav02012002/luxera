# Agent Runtime Contract

Runtime output must include:
1. Plan
2. Diff preview
3. Run manifest
4. Produced artifacts + warnings

Guardrails:
- Never claim compliance without executed job artifacts.
- `apply_diff` and `run_job` require explicit approvals.
- Persist project-scoped memory only (no secrets).
