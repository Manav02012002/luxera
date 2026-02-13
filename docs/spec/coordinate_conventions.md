# Coordinate Conventions (Source of Truth)

This document is the canonical reference for Luxera coordinate and photometry mapping behavior.

## World Axes
- `+X`: horizontal axis.
- `+Y`: horizontal axis orthogonal to `+X`.
- `+Z`: up.

## Luminaire Local Axes
- Local frame is right-handed.
- Local `+Z`: up.
- Emitting/nadir direction is local `-Z`.

## Photometric Angles (Type C)
- `C` is the azimuthal angle in the local `XY` plane.
  - `C=0` points toward local `+X`.
  - `C=90` points toward local `+Y`.
- `gamma` is measured from local nadir (`-Z`) toward zenith (`+Z`).
  - `gamma=0`: straight down.
  - `gamma=90`: horizontal.
  - `gamma=180`: straight up.

## Rotation Model
- Primary/canonical model: Euler ZYX with `(yaw, pitch, roll)` in degrees.
- Composition is `Rz(yaw) * Ry(pitch) * Rx(roll)`.
  - `yaw`: rotation about `+Z`.
  - `pitch`: rotation about `+Y`.
  - `roll`: rotation about `+X`.
- Secondary model: `aim+up`, where local `-Z` is aligned to `aim` and `up` resolves twist.

## Units
- Angles: degrees.
- Length: meters.

## Mapping Pipeline
- `world direction -> luminaire local direction -> photometric angles -> symmetry/interpolation`.
- All transform and photometry mapping entry points must reference this file in docstrings.

## Tilt Policy
- `TILT=INCLUDE` is applied as a multiplicative factor on sampled intensity after angular interpolation.
- The tilt factor is interpolated using the sampled Type-C vertical angle `gamma` (degrees):
  - `I_final_cd = I_interpolated_cd * tilt_factor(gamma_deg)`.
- `TILT=FILE` is currently unsupported and rejected at parse/validation time.

## Invariance Expectations
- Axis sanity:
  - yaw=90 maps local `+X -> +Y`.
  - pitch-only and roll-only rotations follow right-hand rule on `Y` and `X`.
- Field rotation:
  - rotating a luminaire by 90 degrees around `+Z` rotates the illuminance field by 90 degrees.
