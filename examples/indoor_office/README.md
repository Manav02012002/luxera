# Indoor Office Example

This is the canonical indoor workflow example for Luxera.

## Contents
- `office.luxera.json`: project file
- `assets/`: sample public-domain style IES fixtures

## Run End-to-End

From repo root:

```bash
python -m luxera.cli run-all examples/indoor_office/office.luxera.json --job office_direct --report --bundle
```

Or from this folder:

```bash
python -m luxera.cli run-all office.luxera.json --job office_direct --report --bundle
```

## Expected Artifacts

Under `.luxera/results/<job_hash>/`:
- `manifest.json`
- `grid.csv`
- `summary.json`
- `heatmap.png`
- `isolux.png`
- `report.pdf`
- `audit_bundle.zip`
