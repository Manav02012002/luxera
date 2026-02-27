# CIE 171 Validation Plan

This plan tracks the `tests/validation/cie171/` suite skeleton and readiness state.

## Implemented Now (Skeleton Cases)

- `case_direct_room`
- `case_roadway_lane`
- `case_daylight_df`
- `case_emergency_route`

These cases are executable with current Luxera features, but expected reference numbers are intentionally left unpopulated.

## Engine Capabilities Needed Per Case

`case_direct_room`:
- Direct illuminance solver (`job.type=direct`, CPU backend)
- Grid artifact generation (`grid.csv`)
- Deterministic summary metrics extraction

`case_roadway_lane`:
- Roadway workflow (`job.type=roadway`)
- Road luminance/illuminance summary metrics
- Roadway grid artifact generation

`case_daylight_df`:
- Daylight factor mode (`job.type=daylight`, `mode=df`)
- Daylight aperture handling from opening geometry
- Daylight target grid outputs

`case_emergency_route`:
- Emergency workflow (`job.type=emergency`)
- Escape-route and open-area target evaluation
- Emergency summary/compliance payload

## What Remains

- Populate authoritative reference values and tolerance bands in each `expected.json`.
- Add reference artifact files for grid-level residual checks where applicable.
- Map CIE 171 benchmark definitions to Luxera case metadata and traceability fields.
- Expand suite coverage for additional CIE 171 scenarios not yet represented by current skeletons.
- Introduce radiance-backed and multi-engine cross-validation variants where required.

## Reference Fields

Reference-number fields are intentionally left empty in current `expected.json` files and will be populated later.
