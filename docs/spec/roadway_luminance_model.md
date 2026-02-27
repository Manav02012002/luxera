# Roadway Luminance Model

This document defines the roadway luminance model used by Luxera roadway jobs.

## Scope

The model computes pavement luminance from:

1. luminaire photometric intensity distributions (IES/LDT)
2. point/luminaire/observer geometry
3. table-driven road reflection coefficients (`r(beta, tan(gamma))`)

Surface presets are stored in `luxera/data/road_surfaces/`.

## Inputs

- Pavement sample points from roadway grids.
  - For curved segments, longitudinal spacing is along arc length.
  - For banked segments, point coordinates and surface normals include `bank_angle_deg`.
- Observer positions from roadway/grid observer definitions.
- Luminaires with photometry and transforms.
- Road surface class (`R1`/`R2`/`R3`/`R4`).
- Observer profile selection through roadway/grid observer settings:
  - explicit observers (`roadways[].observers` or `roadway_grids[].observers`)
  - auto observers from lane centers using `observer_height_m`, `observer_back_offset_m`, and `observer_method` (for example `en13201_m`)

## Equations

For each observer `o` and pavement point `p`:

- Illuminance contribution from luminaire `i`:
  - `E_i(p)` from Luxera direct illuminance solver (photometric interpolation + inverse-square + incidence cosine).
- Observation geometry:
  - `beta`: angle between horizontal projections of `(luminaire -> point)` and `(point -> observer)`.
  - `tan(gamma) = |v_z| / ||v_xy||` with `v = observer - point`.
- Reflection coefficient lookup:
  - `r_i = interp_table(surface_class, beta, tan(gamma))` (bilinear interpolation).
- Luminance contribution:
  - `L_i(p, o) = E_i(p) * r_i`
- Point luminance:
  - `L(p, o) = sum_i L_i(p, o)`

Reported roadway luminance defaults to the first active observer method row; per-observer view luminance is also reported.

## Reported Outputs

- `road_luminance_mean_cd_m2` (overall mean luminance for the selected observer set)
- Per-lane luminance metrics:
  - `Lavg_cd_m2`
  - `Lmin_cd_m2`
  - `Uo_luminance = Lmin / Lavg`
  - `Ul_luminance = Lmin(line) / Lmax(line)` on configured longitudinal line
- Stable lane-grid payload for reporting/export:
  - `roadway.lanes[i].luminance_grid` ordered by `lane,row,col`

## Stability and Determinism

- Angle domains are clamped to table bounds before interpolation.
- Horizontal-vector degeneracies use deterministic fallback vectors.
- Non-finite intermediate values are guarded and replaced with `0.0`.
- Outputs are serialized with deterministic ordering and stable float formatting in roadway point payloads.
- Summary includes model stability counters (`clamp_count`, `nan_guard_count`).

## Assumptions

- Pavement is a horizontal plane (`+Z` normal).
- Reflection tables are reduced coefficients calibrated per surface class.
- Inter-reflections are not modeled in this stage.
- TI/veiling metrics remain explicit stubs until full glare model implementation.
