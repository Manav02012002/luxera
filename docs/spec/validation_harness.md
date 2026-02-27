# Validation Harness

This document defines the lightweight validation-case framework and CLI used for deterministic regression checks.

## Case Layout

Each case lives under:

`tests/validation/<suite>/<case_id>/`

Required files:
- `scene.lux.json`: runnable Luxera project scene
- `assets/`: photometry/geometry/reference assets
- `expected.json`: reference values, tolerances, and run config
- `README.md`: what the case validates and expected behavior

## `expected.json` Schema (`validation_case_v1`)

Top-level keys:
- `schema_version`: must be `validation_case_v1`
- `run.jobs`: optional list of job ids (defaults to all jobs in scene)
- `reference_source`: optional metadata describing origin of reference values
- `skip.scalars` / `skip.grids`: optional per-metric skip map:
  - key: metric `id`
  - value: `{ "reason": "..." }`
- `scalars`: list of scalar checks
- `grids`: list of grid checks
- `notes`: optional free text

### Scalar check

Fields:
- `id`: metric identifier
- `job_id`: job to evaluate
- `path`: dot-path into job summary (for example `mean_lux`)
- `expected`: numeric reference value
- `tolerance.abs`, `tolerance.rel`: absolute/relative tolerance
- `reference_source` (optional): per-metric source metadata
- `notes` (optional)
- `skip.reason` (optional): skip this metric with reason

### Grid check

Fields:
- `id`: metric identifier
- `job_id`: job to evaluate
- `actual`: artifact file in result dir (for example `grid.csv`)
- `reference`: reference file relative to case dir (for example `assets/reference_grid.csv`)
- `tolerance.max_abs`, `tolerance.mean_abs`, `tolerance.p95_abs`
- `reference_source` (optional): per-metric source metadata
- `notes` (optional)
- `skip.reason` (optional): skip this metric with reason

CSV comparison uses the last numeric column in each row (typically illuminance values).

## CLI

- `python -m luxera.cli validate list`
- `python -m luxera.cli validate run <suite> --out <dir>`
- `python -m luxera.cli validate run <suite>/<case_id> --out <dir>`
- `python -m luxera.cli validate report <suite> --out <dir>`

Outputs are deterministic (sorted ordering, stable float formatting, sorted JSON keys).

## Report Artifacts

`validate report` writes:
- `<suite>_summary.json`
- `<suite>_summary.md`
- Back-compat aliases are also emitted:
  - `validation_<suite>_summary.json`
  - `validation_<suite>_summary.md`

Both include:
- per-case pass/fail
- per-metric errors (absolute and percent)
- grid error summaries (max/mean/p95)
- per-case markdown tables with columns:
  - metric
  - expected
  - actual
  - abs error
  - % error
  - pass/fail/skipped

The JSON artifact is intended for CI ingestion.

## Fast CI Subset

Small validation scaffolding cases are marked with pytest marker `validation_fast`.

Run fast subset:

`pytest -m validation_fast`

Use this marker for tiny deterministic cases suitable for default CI gating.

## CIE171 Smoke CI Gate

Use marker `validation_cie171_smoke` for a minimal CIE171 subset:

`pytest -m validation_cie171_smoke`

CIE171 cases may run in either mode:
- with populated references and tolerances (normal pass/fail)
- with explicit per-metric `skip` reasons when references are unavailable

Skipped metrics are rendered as `SKIPPED` in markdown and include the skip reason.
