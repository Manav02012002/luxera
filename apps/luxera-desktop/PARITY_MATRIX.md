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

### Slice 3: Roadway
- roadway profile/compliance deep breakdown -> `missing`
- roadway luminance/glare tables -> `missing`
- roadway submission artifact preview -> `missing`

### Slice 4: UGR Diagnostics
- `summary.ugr_views` list and per-view diagnostics -> `missing`
- top contributors (`top_contributors`) -> `missing`

### Slice 5: Radiosity Diagnostics
- residual trend / convergence visuals -> `missing`
- energy accounting block (`total_emitted|absorbed|reflected`) -> `missing`
- solver warnings and stop reason detailed panel -> `partial`

## Next Work Order

1. Add table column presets and saved views.
2. Add roadway profile/compliance/luminance/glare panels.
3. Add UGR view + contributor panels.
4. Add radiosity convergence and energy accounting panels.
5. Add result-to-viewport visual linking (select row -> highlight element).
