# Radiosity Validation

This document defines Luxera radiosity validation artifacts and gates.

## Convergence Diagnostics

Radiosity summary emits:
- `iterations`
- `residuals` (per-iteration residual history)
- `energy_balance_history` (per-iteration relative closure error)
- `radiosity_diagnostics`:
  - `iterations_used`
  - `final_residual`
  - `max_residual`
  - `final_energy_balance_rel`
  - `max_energy_balance_rel`

Additional summary checks:
- `residual_threshold` (target threshold from job settings)
- `residual_below_threshold` (boolean)
- `residual_nonincreasing` (boolean)
- `direct_floor_baseline_lux`
- `bounce_delta_lux`
- `bounce_ratio`

## Reference Packs

Diffuse reference packs under `luxera/scenes/refs/`:
- `box_room_diffuse`
- `L_room_diffuse`
- `occluder_room_diffuse`

Each pack includes:
- direct baseline metrics (direct engine)
- radiosity bounce contribution metric (`bounce_ratio`) with tolerance bands
- convergence diagnostics checks (`residual_below_threshold`, residual tolerance)

## Determinism Gate

`tests/gates/test_radiosity_convergence_gate.py` enforces:
- deterministic residual history for fixed seed
- deterministic energy-balance history for fixed seed
- non-increasing residual history for validation scene
