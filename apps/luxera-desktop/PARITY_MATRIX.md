# Desktop Parity Matrix (Backend -> Frontend)

Status keys:
- `wired`: rendered in desktop UI.
- `partial`: available but not fully represented.
- `missing`: produced by backend but not surfaced in desktop yet.

## Current Backend Contracts

Files emitted by runner:
- `result.json` (primary summary + warnings/compliance metadata)
- `tables.json` (grid/plane/point-set aggregate tables)
- `results.json` (job-type specific structured payloads)

## Mapping Status

### Slice 0: Project Lifecycle
- project init/open/save flow (desktop command surface + editor) -> `wired`
- project schema validation (all jobs or selected job) -> `wired`

### Slice 0.5: Geometry Authoring
- add rectangular room (project mutation via CLI) -> `wired`
- geometry import (DXF/OBJ/GLTF/FBX/SKP/IFC/DWG) -> `wired`
- geometry clean + detect rooms -> `wired`

### Slice 0.75: Luminaire Authoring
- photometry asset import (IES/LDT) -> `wired`
- luminaire placement with transform/maintenance/tilt -> `wired`

### Slice 1.0: Calculation Setup
- calc grid creation -> `wired`
- job creation (type/backend/seed) -> `wired`

### Slice 1.25: Export / Reporting
- debug bundle export -> `wired`
- client bundle export -> `wired`
- backend comparison export -> `wired`
- roadway report export -> `wired`

### Slice 1.5: Agent Interface
- agent intent execution (`AgentRuntime.execute`) -> `wired`
- approvals payload + structured response inspection -> `wired`

### Slice 1: Summary / Warnings / Compliance
- `result.summary.mean_lux|min_lux|max_lux|uniformity_ratio` -> `wired`
- `result.summary.highest_ugr|ugr_worst_case` -> `wired`
- `result.summary.compliance.status|reasons` -> `wired`
- `result.photometry_verification.warnings` -> `wired`
- `result.photometry_warnings[*]` -> `wired`
- `result.near_field_warnings[*]` -> `wired`
- `result.summary.solver_status.warnings` -> `wired`
- backend metadata (`job.type`, `backend.name`, `solver.package_version`) -> `wired`

### Slice 2: Table/Zone Outputs
- `tables.grids|vertical_planes|point_sets` counts -> `wired`
- full table row rendering / sort / filter -> `wired`
- `summary.indoor_planes` deep rendering -> `wired`
- zone metrics deep rendering (`zone_metrics`, `zones` table) -> `wired`
- full raw JSON field explorer (`result|tables|results`) -> `wired`
- `results.engines[*].summary` inventory -> `wired`

### Slice 3: Roadway
- roadway profile/compliance deep breakdown -> `wired`
- roadway luminance/glare tables -> `wired`
- roadway submission artifact preview -> `wired`

### Slice 4: UGR Diagnostics
- `summary.ugr_views` list and per-view diagnostics -> `wired`
- top contributors (`top_contributors`) -> `wired`

### Slice 5: Radiosity Diagnostics
- residual trend / convergence visuals -> `wired`
- energy accounting block (`total_emitted|absorbed|reflected`) -> `wired`
- solver warnings and stop reason detailed panel -> `wired`

## Next Work Order

1. Add table column presets and saved views.
