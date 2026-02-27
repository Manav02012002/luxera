# Roadway Metrics

Defines roadway luminance metrics and reporting artifacts for roadway jobs.

## Stable Output Schema

Roadway jobs publish a canonical roadway block in `results.json`:

- `roadway.method`
  - selected method/profile label used for evaluation (profile id when available, otherwise road class).
- `roadway.lanes[i].luminance_grid`
  - ordered point list (`lane_row`, `lane_col`, deterministic `order`, coordinates, illuminance, luminance).
- `roadway.lanes[i].metrics`
  - `Lavg`
  - `Lmin`
  - `Uo`
  - `Ul`
- `roadway.metrics`
  - `worst_case`
  - `worst_case_glare`

## Lane Metrics

For each lane, using lane luminance samples `L` (cd/m2):

- `Lavg`:
  - arithmetic mean of all lane luminance samples.
- `Lmin`:
  - minimum luminance in lane.
- `Uo`:
  - `Lmin / Lavg`, where `Lmin` is minimum luminance in lane.
- `Ul`:
  - computed along a defined longitudinal line within lane.
  - line policy is controlled by `settings.luminance_longitudinal_line`:
    - `center` (default): center row
    - `first`: first row
    - `last`: last row
    - integer index: explicit row index (clamped)
  - `Ul = Lmin_line / Lmax_line`.

Legacy lane aliases are retained in summary payloads (`Lavg_cd_m2`, `Lmin_cd_m2`, `Uo_luminance`, `Ul_luminance`) for compatibility.

## Worst-Case Summaries

Roadway summary emits canonical worst-case structures:

- `roadway.metrics.worst_case` (aliases: `roadway_worst_case`, `luminance_worst_case`)
  - `lavg_min_cd_m2`
  - `uo_min`
  - `ul_min`
  - lane indices for each worst-case metric (`lane_lavg_min`, `lane_uo_min`, `lane_ul_min`)

- `roadway.metrics.worst_case_glare` (alias: `worst_case_glare`)
  - worst observer and glare metric summary per selected glare method

## Artifacts

Roadway runs emit per-lane luminance grids:

- `road_luminance_grid_<lane>.csv`
  - columns: `x,y,z,luminance_cd_m2`

Existing illuminance lane CSVs remain:

- `road_grid_<lane>.csv`
  - columns: `x,y,z,illuminance`

Determinism guarantees:

- lane ordering: ascending `lane_index`, then `lane_number`
- grid-point ordering: `lane_row`, then `lane_col`, then `order`
- glare contribution ordering (if stored): `luminaire_index`, `theta_deg`, distance, intensity

## Reporting

Roadway HTML/PDF reports include:

- lane luminance table (`Lavg`, `Lmin`, `Lmax`, `Uo`, `Ul`)
- worst-case luminance summary table
