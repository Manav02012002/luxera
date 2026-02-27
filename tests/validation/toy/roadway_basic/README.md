# Toy Roadway Basic

Validates a tiny deterministic roadway scene.

Checks:
- Scalar roadway summary metrics (`mean_lux`, `uniformity_ratio`, `road_luminance_mean_cd_m2`)
- Grid artifact regression against a reference CSV (`grid.csv`)

Purpose:
- Fast CI-level harness sanity for roadway workflow and grid comparator.
