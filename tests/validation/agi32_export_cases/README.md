# AGI32 Export Parity Cases

This directory stores strict AGI32-export-backed parity cases.

## Requirements

1. Each case file must be named `case_*.json`.
2. `expected.provenance.source` must be `agi32_export`.
3. Raw AGI32 export files referenced by provenance must be checked in.
4. SHA256 hashes in provenance must match the raw files exactly.

## Case Schema

Top-level:

1. `id`
2. `room`
3. `luminaires`
4. `grid`
5. `expected`

`expected` fields:

1. `min_lux`
2. `max_lux`
3. `avg_lux`
4. `uniformity_u0`
5. `tolerances`
6. `provenance`

`expected.provenance` required fields:

1. `source` = `agi32_export`
2. `tool` (for example `AGI32`)
3. `tool_version`
4. `export_date` (ISO date)
5. `raw_summary_file`
6. `raw_summary_sha256`

Optional grid provenance:

1. `raw_grid_file`
2. `raw_grid_sha256`

## Validation

Run:

```bash
pytest -q tests/validation/test_agi32_export_parity_cases.py -x
```

The test validates provenance integrity and numerical parity against Luxera direct illuminance outputs.
