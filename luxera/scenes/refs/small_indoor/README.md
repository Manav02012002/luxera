# Small Indoor Parity Pack

Intent: deterministic baseline for a single-room direct illuminance workflow.

## Scene
- 6m x 6m x 3m rectangular room
- One luminaire at center-ish ceiling position
- One horizontal workplane grid (`5 x 5`)
- One engine/job: `direct_cpu` (`job_direct_cpu`)

## Expected Metrics
See `expected/expected.json` for the parity contract and tolerances. Core checked metrics include:
- `mean_lux`
- `min_lux`
- `max_lux`
- `uniformity_ratio`
- `occluder_count`

## Notes
This pack is intentionally small and fast to keep parity regression runtime low.
