# Roadway Grid Definition (v1)

This document defines the deterministic roadway grid contract used by `roadway` jobs.

## Inputs

- `roadway_grid.nx` or `roadway_grid.longitudinal_points` for longitudinal sampling.
- `roadway_grid.ny` or `roadway_grid.num_lanes * roadway_grid.transverse_points_per_lane` for transverse sampling.
- Geometry comes from:
  - linked `roadway` object when `roadway_grid.roadway_id` is set, or
  - raw `roadway_grid` dimensions otherwise.

## Effective Grid

- `road_length_m` is derived from linked roadway start/end when present, otherwise `roadway_grid.road_length`.
- `lane_width_m` and `num_lanes` are sourced from linked roadway when present, otherwise roadway grid fields.
- Grid origin is roadway `start` when linked, otherwise `roadway_grid.origin`.
- Overall road calculation grid has:
  - `width = road_length_m`
  - `height = lane_width_m * num_lanes`
  - `nx = longitudinal sample count`
  - `ny = transverse sample count`

## Lane Slicing

- The transverse grid is partitioned into `num_lanes` contiguous lane bands.
- Per-lane metrics are reported under `summary.lane_metrics`.
- Per-lane CSV artifacts are emitted as:
  - `road_grid_1.csv`
  - `road_grid_2.csv`
  - ...

## Output Contract

Roadway result summary includes:

- overall: `mean_lux`, `min_lux`, `max_lux`, `uniformity_ratio`, `ul_longitudinal`
- geometry: `lane_width_m`, `num_lanes`, `road_length_m`
- lane metrics list: each lane row contains:
  - `lane_index`, `lane_number`
  - `mean_lux`, `min_lux`, `max_lux`
  - `uniformity_ratio`, `uniformity_min_avg`, `ul_longitudinal`
  - `sample_count`, `nx`, `ny`

## Determinism

- For identical project/job payloads and seed, lane metrics and per-lane CSV artifacts must be identical across runs.
