# Validation Policy

## Scope
- CPU direct illuminance remains the primary deterministic reference solver.
- Radiance comparison tests validate small canonical scenes for directional agreement and magnitude sanity.

## Radiance Comparison
- Marker: `radiance`.
- Canonical scene: small enclosed room, one luminaire, fixed workplane grid.
- Metrics:
  - Mean absolute relative error between CPU and Radiance lux values.
  - Mean illuminance delta between CPU and Radiance.
- Default tolerance target in validation tests: `<= 5%` mean relative error for mocked/synthetic fixtures.

## Known Differences
- CPU path uses direct point sampling with Luxera interpolation and occlusion policy.
- Radiance path includes RGB-to-lux conversion and command-line solver settings.
- Small deviations are expected from sampling, color conversion, and scene proxying.

## Reproducibility
- Tests are deterministic:
  - Fixed geometry and photometry fixture.
  - Fixed grid definition.
  - Stable mocked Radiance CLI output in automated validation runs.
