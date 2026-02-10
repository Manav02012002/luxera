# Runner Persistence Contract

## Chosen Model
Option A: `run_job(project_path, job_id)` is the public contract.

- Runner loads project from path.
- Runner writes immutable result artifacts under `.luxera/results/<job_hash>/`.
- Runner updates `project.results` with a `JobResultRef`.
- Runner persists project schema back to disk before returning.

## Enforcement
- CLI and GUI call the path-based runner API directly.
- Legacy/in-memory runner path is explicit (`run_job_in_memory`) and used only where project object workflows are required.

## Artifact Metadata Requirements
Each `result.json` includes:
- job id/hash + seed
- project schema version
- job settings + effective settings + settings dump
- solver/backend versions
- photometry asset hashes
- units + coordinate convention
- assumptions + unsupported feature disclosures
