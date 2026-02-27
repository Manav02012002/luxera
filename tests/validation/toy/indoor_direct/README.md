# Toy Indoor Direct

Validates a tiny deterministic direct illuminance scene.

Checks:
- Scalar summary metrics (`mean_lux`, `min_lux`, `max_lux`)
- Grid artifact regression against a reference CSV (`grid.csv`)

Purpose:
- Fast CI-level harness sanity for direct solver contract and comparison pipeline.
