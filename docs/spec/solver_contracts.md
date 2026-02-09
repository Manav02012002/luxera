# Solver Contracts

## Input Contract
A run is fully defined by:
- Project schema payload (`schema_version` + normalized project data)
- Job spec (`id`, `type`, `backend`, `settings`, `seed`)
- Photometry content hashes for all referenced assets
- Coordinate convention and units contract

## Output Contract (`result.json`)
Mandatory fields:
- `contract_version`
- `project.{name,schema_version}`
- `job_id`, `job_hash`, `job` (raw), `effective_settings`, `seed`
- `assets` (asset_id -> content hash)
- `backend.{name,version}`
- `solver` (package + source control id when available)
- `units`
- `coordinate_convention`
- `summary`
- backend-specific provenance (`backend_manifest` and execution command lines when applicable)

## Determinism
- Identical project state + job spec + seed must produce same job hash.
- Result artifacts are immutable per `job_hash` directory.
- Existing `result.json` for a job hash is reused.

## Direct Occlusion Model
- Optional hard-shadow model for direct jobs (`use_occlusion`).
- Rays are tested from luminaire to calculation point against planar occluder surfaces.
- Uses geometric intersection with epsilon controls (`occlusion_epsilon`).

## Coordinate Convention
- Local luminaire frame: `+Z up`, nadir `-Z`
- `C=0` toward local `+X`, `C=90` toward local `+Y`

## Units
- Length: `m`
- Illuminance: `lux`
- Luminous intensity: `cd`
- Luminous flux: `lm`
- Angles: `deg`
