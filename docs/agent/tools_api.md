# Agent Tools API

Only these operations are allowed for runtime execution:
- Project: `open_project`, `save_project`, `validate_project`, `diff_preview`, `apply_diff`
- Assets: `add_asset`, `inspect_asset`, `hash_asset`
- Geometry: `import_geometry`, `clean_geometry`
- Jobs/Results: `add_grid`, `add_job`, `run_job`, `summarize_results`, `render_heatmap`
- Reports/Bundles: `build_pdf`, `export_client_bundle`, `export_debug_bundle`, `export_backend_compare`

Guardrails:
- `apply_diff` and `run_job` require explicit approval.
- Runtime must use tool calls for all state-changing actions.
