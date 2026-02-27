# Photometry Type B Transform

This spec defines Luxera's Type B coordinate transform behavior in the canonical luminaire-local frame.

## Canonical Local Frame

- `+X`: luminaire length axis
- `+Y`: luminaire width axis
- `+Z`: up
- Nadir/emission reference is along `-Z` for Type C workflows.

Type B uses:
- Polar axis `p = +Y`
- Horizontal zero-reference direction `e0` from projection of `-Z` onto the plane normal to `p`
- Horizontal angles are clockwise about `+p` per LM-63 conventions

## Direction -> Type B Angles

Given unit local direction `d`:

1. Build basis:
- `p = +Y`
- `e0 = normalize((-Z) - dot(-Z,p)*p)`
- `e90 = normalize(cross(p, e0))`

2. Horizontal angle `H`:
- `d_perp = d - dot(d,p)*p`
- if `||d_perp|| == 0`, `H = 0`
- else `ccw = atan2(dot(normalize(d_perp), e90), dot(normalize(d_perp), e0))`
- `H = (-ccw) mod 360`

3. Vertical angle `V` mode:
- Elevation-mode datasets (`min(V) < 0` or `max(V) <= 90`):
  - `V = atan2(dot(d,p), ||d_perp||)`
- Polar-mode datasets (typically `0..180`):
  - `V = acos(clamp(dot(d,p), -1, 1))`

## Type B Angles -> Direction (inverse)

Used for validation/scaffold tests:

- Convert to polar angle from `+p`:
  - elevation mode: `beta = 90 - V`
  - polar mode: `beta = V`
- `ccw = -H`
- `radial = e0*cos(ccw) + e90*sin(ccw)`
- `d = p*cos(beta) + radial*sin(beta)`

## Determinism

- All transforms are pure, deterministic, and numeric-stable.
- Angle normalization uses explicit clamping and `% 360` normalization.

## Tests

- Synthetic equivalence test: rotationally symmetric field encoded as Type C and Type B yields matching sampled intensities.
- Corpus-backed Type B fixture test verifies expected directional beam ordering.
- Transform path is exercised through world-space sampling (`sample_intensity_cd_world`) and local sampling (`sample_intensity_cd`) with the same canonical local basis.
