# Roadway Luminance Metrics Pack

Intent:

- Regression guard for roadway lane luminance metrics and worst-case summaries.
- Verifies stable roadway output schema under `roadway.*` in parity `results.json`.

Expected focus:

- `roadway.method`
- `roadway.lanes[].metrics.{Lavg,Lmin,Uo,Ul}`
- `roadway.metrics.worst_case`
- deterministic lane ordering and lane grid ordering

