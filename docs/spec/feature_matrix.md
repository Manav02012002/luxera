# Feature Matrix

This matrix defines product scope at a contract level.

## Indoor
- Direct illuminance grids (horizontal, vertical, point sets): `supported`
- Radiosity/interreflections (deterministic seed): `supported with limits`
- EN 12464 checks from computed results: `supported`

## Roadway
- Roadway grid workflow + class/profile threshold checks + observer-view luminance: `supported with limits`

## Emergency
- Emergency electric-lighting workflow + threshold checks: `supported with limits`

## Glare
- UGR workflow (documented assumptions, observer sets): `supported with limits`

## Daylight
- Daylight-factor + annual proxy DA/sDA/UDI workflow: `supported with limits`

## Agentic Assistance
- Project diff proposal/apply via tool API: `supported`
- Guardrailed execution with approvals: `supported`
