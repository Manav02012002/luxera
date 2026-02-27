# Small Roadway Parity Pack

Intent: placeholder parity pack for roadway workflow and report surface.

## Scene
- One roadway segment
- One roadway grid (`4 x 4`)
- One luminaire
- One engine/job: `roadway_cpu` (`job_roadway_cpu`)

## Expected Metrics
See `expected/expected.json` for tolerance-aware assertions. Core checked metrics include:
- `mean_lux`
- `uniformity_ratio`
- `road_luminance_mean_cd_m2`
- `ul_longitudinal`

## Notes
This pack is a compact regression anchor for roadway summary contract stability.
