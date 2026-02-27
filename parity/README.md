# Parity Corpus (Repo Root)

This folder is the repo-root parity corpus. It can hold pack metadata, scene assets, expected baselines, tolerance presets, and CI selections.

## Layout

- `parity/packs/<pack_id>/pack.yaml`: pack manifest
- `parity/packs/<pack_id>/scenes/`: scene files (`.lux.json`)
- `parity/packs/<pack_id>/assets/`: photometry/geometry assets
- `parity/packs/<pack_id>/expected/luxera/v1/`: Luxera expected outputs
- `parity/tolerances/`: shared tolerance profiles
- `parity/ci/`: fast/nightly selector files
- `parity/tools/`: helper scripts

## Running Parity

Example commands:

- `python -m luxera.cli parity run --pack indoor_basic --baseline luxera --out out/parity_runs/indoor_basic`
- `python -m luxera.cli parity run --selector parity/ci/fast_selection.yaml --baseline luxera --out out/parity_runs/fast`
- `python -m luxera.cli parity update --pack indoor_basic --baseline luxera --out out/parity_runs/update`

### Invariance Packs

Packs can enable transform invariance checks in `pack.yaml`:

```yaml
global:
  random_seed: 42
  deterministic: true
  invariance: true
```

When enabled, parity auto-runs transformed variants per scene:
- large translation
- Z-rotation (90 deg)
- unit-equivalent mm conversion

Failures are reported in `summary.md` with transform, metric, and error magnitude.

## Adding A Scene To A Pack

1. Add scene file under `parity/packs/<pack_id>/scenes/` (for example `office_01.lux.json`).
2. Add required assets under `parity/packs/<pack_id>/assets/`.
3. Add scene entry in `pack.yaml` under `scenes:`.
4. Add/refresh expected results in `parity/packs/<pack_id>/expected/luxera/v1/`.
5. Add the pack to `parity/ci/fast_selection.yaml` or `parity/ci/nightly_selection.yaml` when ready.
