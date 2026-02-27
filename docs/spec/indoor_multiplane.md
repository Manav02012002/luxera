# Indoor Multi-Plane Calculation Spec

Luxera indoor direct workflow supports multi-target illuminance outputs for:

- horizontal workplane grids (existing `grids`)
- polygon workplanes (`polygon_workplanes`) sampled over arbitrary in-plane polygons
- vertical illuminance planes
: user-defined planes from `vertical_planes`
: optional auto-generated wall planes (`auto_vertical_planes=true`)
- route/line calculations (`line_grids`) sampled along polyline centerlines
- cylindrical illuminance at grid points (optional)

## Job Settings

Direct job settings additions:

- `maintenance_factor` (MF, default `1.0`)
- `auto_vertical_planes` (default `false`)
- `auto_vertical_plane_nx` (default `9`)
- `auto_vertical_plane_ny` (default `5`)
- `compute_cylindrical_illuminance` (default `false`)

## Maintained Factor (MF)

Maintained illuminance is modeled as a deterministic scaling of source output:

- Per luminaire: `flux_multiplier * maintenance_factor` from luminaire instance
- Global direct-job factor: `maintenance_factor` from job settings

Effective source scaling is applied before point sampling.

## Vertical Plane Generation

### User-defined
- Uses `vertical_planes` entries directly.
- Host-surface mode is supported for opening masking.
- `offset_m` shifts the sampled vertical plane along its surface normal.

## Polygon Workplane Sampling

- `polygon_workplanes` define:
  - plane frame (`origin`, `axis_u`, `axis_v`)
  - polygon mask in UV (`polygon_uv`, optional `holes_uv`)
  - target sample count (`sample_count`)
- Sampling uses deterministic stratification in UV space with seed-driven jitter and polygon/hole masking.
- The same scene + seed yields identical sample points and ordering.

## Route / Line Sampling

- `line_grids` define a 3D polyline + fixed spacing.
- Sampling is deterministic, includes segment endpoints, and includes the terminal endpoint of the full route.

### Auto walls
When enabled, planes are generated from:
1. wall surfaces in scene geometry (`kind="wall"`), or
2. rectangular room shell fallback (first room) when explicit wall surfaces are absent.

## Cylindrical Illuminance

Cylindrical illuminance at each grid point is approximated as:

`E_cyl = (E(+X) + E(-X) + E(+Y) + E(-Y)) / 4`

where each `E(direction)` is direct illuminance sampled with a vertical surface normal in that direction.

## Output Contract

`result.json -> summary.indoor_planes` contains:

- `maintenance_factor`
- `per_plane[]` with per-target metrics:
  - `Eavg`
  - `Emin`
  - `U0`
  - plus `id`, `type`, `source`
- `cylindrical[]` (when enabled) with:
  - `Eavg`
  - `Emin`
  - `U0`
  - plus `id`, `type`

Aliases are also retained in per-object summaries (`mean_lux`, `min_lux`, `uniformity_ratio`).
