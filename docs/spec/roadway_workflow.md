# Roadway Workflow (v1)

## Supported Flow
1. Add roadway grid geometry (`lane_width`, `road_length`, `nx`, `ny`, plus optional `num_lanes`, `pole_spacing_m`, `mounting_height_m`, `setback_m`, `observer_height_m`).
2. Add luminaires with IES/LDT assets.
3. Run roadway job (`type=roadway`) for deterministic illuminance metrics.
4. Export roadway HTML report via CLI:
   - `luxera.cli export-roadway-report <project> <job_id> --out roadway.html`

## Metrics
- Mean/min/max illuminance
- Overall uniformity (`uniformity_ratio`)
- Longitudinal uniformity (`ul_longitudinal`)
- Mean roadway luminance proxy (`road_luminance_mean_cd_m2`)
- Observer luminance view table

## Compliance
If a roadway compliance profile is selected, report includes threshold checks:
- `avg_min_lux`
- `uo_min`
- `ul_min`
- `luminance_min_cd_m2`

## Current Scope
- Fast deterministic illuminance-based roadway analysis (v1)
- Luminance/glare full photometric roadway model is planned for v2
