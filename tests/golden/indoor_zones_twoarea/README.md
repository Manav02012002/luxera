# Indoor Two-Zone Golden Pack

This pack validates indoor zoning for task and surrounding areas on a horizontal workplane.

- `zone_task`: central task polygon with stricter requirements.
- `zone_surround`: surrounding polygon with independent requirements.

The direct job uses `settings.zone_requirements` to apply per-zone thresholds and emits per-zone metrics/compliance in `summary.zone_metrics` and `tables.json`.
