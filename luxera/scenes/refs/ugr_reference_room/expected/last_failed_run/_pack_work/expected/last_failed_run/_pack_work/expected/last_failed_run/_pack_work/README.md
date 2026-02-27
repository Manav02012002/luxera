# UGR Reference Room

Intent: stable UGR regression pack for radiosity + explicit glare view.

Checks:
- `summary.ugr_worst_case` stays within tolerance.
- `summary.ugr_debug.top_contributors` ordering is deterministic.
- Contributor rows use explainable fields: `luminaire_id`, `omega`, `luminance_est`, `position_index`, `contribution`.

This pack enables report debug appendix (`ugr_debug_appendix=true`) for UGR explainability output.
