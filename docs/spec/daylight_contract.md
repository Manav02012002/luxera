# Daylight Contract

This document defines daylight job behavior for `df` and Radiance-backed modes.

## Modes
- `df`: deterministic daylight-factor baseline.
- `radiance`: physically based daylight sampling through Radiance integration.

## Sky Model
- Supported sky labels: `CIE_overcast`, `CIE_clear`, `CIE_intermediate`.
- Initial default is `CIE_overcast`.

## Core Metrics
- Daylight Factor: `DF = 100 * Ei / Eo`.
- `Eo` is external horizontal illuminance (lux).
- Outputs may be DF (%) and/or illuminance (lux), depending on mode/report target.

## Apertures
- Daylight apertures are explicit geometry openings with visible transmittance.
- Missing aperture definitions are validation errors.

## Determinism
- DF mode is deterministic.
- Radiance mode must pin quality and seed parameters to provide reproducible outputs.
