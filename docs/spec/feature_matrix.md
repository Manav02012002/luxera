# Feature Matrix

This matrix defines product scope at a contract level.
Status labels:
- `verified`: implemented and externally/contract-validated for release claims
- `not_supported`: not ready for professional release claims

## Indoor
- Direct illuminance grids (horizontal, vertical, point sets): `verified`
- Radiosity/interreflections (deterministic seed): `not_supported`
- EN 12464 checks from computed results: `verified`

## Roadway
- Roadway grid workflow + class/profile threshold checks + observer-view luminance: `not_supported`

## Emergency
- Emergency electric-lighting workflow + threshold checks: `not_supported`

## Glare
- UGR workflow (documented assumptions, observer sets): `not_supported`

## Daylight
- Daylight-factor + annual proxy DA/sDA/UDI workflow: `not_supported`

## Agentic Assistance
- Project diff proposal/apply via tool API: `verified`
- Guardrailed execution with approvals: `verified`
