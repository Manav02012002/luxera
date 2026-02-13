# Photometry Contracts

This document defines non-negotiable photometry behavior.

## Photometric Type
- Supported runtime type: `Type C` only.
- `Type A`/`Type B` inputs must fail validation with actionable errors.

## Tilt
- Supported tilt sources: `NONE`, `INCLUDE`, `FILE`.
- Tilt factors are applied against Type C `gamma` angle.
- Interpolation is linear.
- Out-of-range tilt angles clamp to endpoint factors.

## Units
- Internal runtime length unit is meters.
- Input coordinate/geometry scales must be normalized via `scale_to_meters` before distance-dependent calculations.

## Symmetry and Tables
- Vertical/horizontal angle counts must match candela-table dimensions.
- Horizontal-angle conventions must be explicitly validated (including origin/monotonicity rules used by parser).

## Interpolation
- Intensity sampling is deterministic and pure (same input -> same output).
- Angular interpolation behavior is documented and stable across releases.
