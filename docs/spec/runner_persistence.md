# Runner Persistence Contract

## Chosen Model
Option B: `run_job(project, job_id)` is pure with respect to file I/O for project schema.

- Runner writes immutable result artifacts under `.luxera/results/<job_hash>/`.
- Runner mutates in-memory `project.results` with a `JobResultRef`.
- Caller is responsible for persisting project schema (`save_project_schema`) after successful runs.

## Enforcement
- CLI run path saves project immediately after `run_job`.
- GUI run path saves project immediately after `run_job`.
- Agent runtime saves project after tool execution.

## Artifact Metadata Requirements
Each `result.json` includes:
- job id/hash + seed
- project schema version
- job settings + effective settings + settings dump
- solver/backend versions
- photometry asset hashes
- units + coordinate convention
- assumptions + unsupported feature disclosures
