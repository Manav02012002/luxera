# Roadway Deterministic Grids

This document defines the roadway deterministic sampling contract used by roadway jobs.

## Scene Schema Additions

`roadways[]` supports optional nested structures:

- `segment`
  - `length_m` (optional override)
  - `lane_count` (optional override)
  - `lane_widths_m` (per-lane widths)
  - `lateral_offset_m`, `vertical_offset_m`
  - `curve_radius_m`, `curve_angle_deg`, `curve_direction` (`left`/`right`)
  - `bank_angle_deg` (superelevation)
- `pole_rows[]`
  - `id`, `side`, `spacing_m`, `offset_m`, `mounting_height_m`, `tilt_deg`, `aim_deg`, `count`
- `observers[]`
  - `id`, `lane_number`, `method`, `enabled`, `height_m`, `back_offset_m`, `lateral_offset_m`, `notes`

`roadway_grids[]` adds:

- `observer_method`
- `observers[]` (same schema as roadway observer definitions)

## Deterministic Ordering

Lane grid ordering is stable and documented as:

- lane index ascending
- within each lane: row-major (`lane,row,col`)
- points include explicit `order`, `lane_row`, `lane_col`

`result.json` includes `roadway_results` and roadway jobs also emit `results.json` with:

- `metadata` (`method`, `road_class`, `units`)
- `lane_grids[]` (ordered point lists)
- `observer_sets`
  - `luminance`
  - `ti` (computed TI rows when glare observers are active)
  - `ti_stub` (only when TI observers are declared but glare is not computed)

## Grid Types

Implemented deterministic sets:

- pavement luminance/illuminance lane grids
- curved-road longitudinal spacing measured along arc length when curve segment is configured
- banked roadway sampling where point Z and surface normals include `bank_angle_deg`
- observer sets for luminance sampling
- TI observer rows from glare pipeline (plus stub mode fallback)

## Stability Rules

- JSON objects are written with sorted keys.
- Scalar point coordinates/values in roadway point lists use stable float formatting.
- Lane slicing is deterministic even when `ny` is not perfectly divisible by lane count.
