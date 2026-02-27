# Agent Planner

## Goal

Replace keyword-branch runtime dispatch with planner-driven tool execution.

Planner flow:

1. Build compact project context summary.
2. Expose JSON schemas for all registered tools from the tool registry.
3. Planner returns an ordered tool-call plan.
4. Runtime executes calls sequentially with step logs and intermediate result capture.
5. Runtime enforces approval gates for mutating/apply/run actions.

## Planner Interface

Input:

- `intent`: raw user intent string
- `project_context`: compact summary from `project.summarize`
- `agent_memory`: rolling structured context memory (injected under `project_context.agent_memory`)
- `tool_schemas`: JSON schemas generated from the registry

Output:

- ordered tool calls: `[{tool, args}, ...]`
- rationale string

Implemented backends:

- `RuleBasedPlannerBackend`: deterministic default planner
- `MockPlannerBackend`: deterministic canned plans for tests

## Tool Schema Generation

`AgentToolRegistry` generates JSON schemas automatically from function signatures.

- source of truth: registered tool callable signature
- includes required/optional params and primitive type mapping
- stable ordering via `json_schemas()` for deterministic snapshots

## Execution Contract

Runtime executes planner calls in order and records:

- `step_logs`: per-step status and message
- `intermediate_results`: per-step tool output payloads
- `tool_calls`: executed calls and statuses

These are stored in:

- session artifact (`.luxera/agent_sessions/<runtime_id>.json`)
- runtime manifest payload (`run_manifest.step_logs`, `run_manifest.intermediate_results`)

## Context Memory

Persistent memory artifact:

- `.luxera/agent_context.json` (project-local)

Rolling summary fields:

- `geometry`
- `luminaires`
- `targets`
- `last_results`
- `failed_constraints`
- `user_preferences`

CLI:

- `luxera agent context show <project.json>`
- `luxera agent context reset <project.json>`

## Diff + Approval Gating

Runtime always emits a diff proposal payload (`diff_preview`).

For mutation application:

- planner may propose a diff-producing step (`project.diff.propose_layout`, optimizer diff, option diff)
- `project.diff.apply` is blocked unless `approvals.apply_diff == true`
- selected diff-op filtering is supported via `approvals.selected_diff_ops`

For calculations:

- `job.run` / `run_calc` are blocked unless `approvals.run_job == true`

The runtime response always includes required approval actions (`apply_diff`, `run_job`) when applicable.
