# Emergency Contract

This document defines emergency-lighting workflow expectations.

## Standards Scope
- Profiles target EN 1838 / BS 5266 style criteria.
- Route and open-area metrics are evaluated against configured thresholds.

## Inputs
- Emergency mode defines luminaire subset and emergency output factor.
- Escape routes are explicit polyline definitions with spacing/width parameters.
- Open-area targets reference existing calculation grids.

## Outputs
- Per-route samples and summary statistics: min/avg/max and `U0 = min/avg`.
- Open-area summaries with threshold pass/fail.
- Manifest includes selection policy, emergency factor, and thresholds used.

## Determinism
- Sampling and evaluation are deterministic for fixed inputs.
