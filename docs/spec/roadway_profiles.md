# Roadway Profiles

Defines data-driven roadway profiles for common-practice compliance checks.

## Data Location

- `luxera/standards/roadway/profiles.json`
- `luxera/standards/roadway/requirements/*.csv`

Legacy compatibility loader paths remain supported:
- `luxera/standards/roadway/data/profile_configs.json`
- `luxera/standards/roadway/data/requirements_table.csv`

No metric thresholds are hardcoded in evaluation code.

## Structure

`profiles.json` stores profile metadata:
- `id`
- `name`
- `standard_ref`
- `domain`
- `class`
- `notes`
- `requirements_table` (path to CSV requirements file)

Repository includes one explicit non-standard placeholder profile:

- `demo_nonstandard_placeholder`
- intended only for machinery tests/demos
- not a standards-compliance profile

Each requirements CSV stores checks:
- `metric`
- `comparator` (`>=` or `<=`)
- `target`
- `units`

## Scene Selection

Roadway jobs can select a standards profile via settings:

- `roadway_profile_id` (preferred)
- `roadway_profile` (alias)
- scene-level roadway object:
  - `roadways[i].profile` (used when job setting is not provided)

If no standards profile is selected, legacy project `compliance_profile_id` behavior remains supported.

## Outputs

Roadway summary includes:
- `roadway_profile`
- `compliance.status`
- `compliance.checks[]`
- `compliance.thresholds`
- `compliance.margins`
- canonical roadway method binding:
  - `roadway.method` (profile id when selected, fallback to road class)
- canonical roadway lane metrics:
  - `roadway.lanes[].metrics.{Lavg,Lmin,Uo,Ul}`
- canonical worst-case buckets:
  - `roadway.metrics.worst_case`
  - `roadway.metrics.worst_case_glare`

Roadway artifacts include submission-style files:
- `roadway_submission.json`
- `roadway_submission.md`

Reports include a submission-style summary table with metric, target, margin, and pass/fail.
