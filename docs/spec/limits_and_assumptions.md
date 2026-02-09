# Limits and Assumptions

## Photometry
- IES Type C: supported.
- IES Type B/A: parser accepts values where present; full production treatment must be explicitly validated before claiming support.
- LDT: supported with conversion-factor scaling.

## Glare
- UGR currently computed with documented default observer heights and spacing.
- Background luminance and luminaire luminance model are simplified.

## Reflectance / Materials
- Broadband scalar reflectance model is primary.
- RGB/spectral extensions are placeholders until explicitly added to schema/contracts.

## Radiosity
- Separate job type with explicit convergence thresholds and patch subdivision controls.
- Determinism depends on persisted seed and fixed sampling parameters.

## Direct Shadowing / Occlusion
- Direct occlusion is currently hard-shadow (binary blocked/unblocked), not penumbra/area-light shadowing.
- Occlusion depends on provided planar surface geometry quality (normals/winding/topology).
- For production use, run geometry cleaning and non-manifold checks before occlusion-heavy studies.

## Roadway
- Roadway workflow evaluates illuminance/uniformity and observer-view road luminance (Lambertian road model) on roadway grids.
- Full roadway glare/discomfort indices are not yet implemented.

## Emergency
- Emergency workflow evaluates thresholds across battery decay over configured duration (linear/exponential curve).
- Per-luminaire battery heterogeneity and failure distributions are not yet implemented.

## Daylight
- Daylight workflow supports daylight-factor and annual proxy DA/sDA/UDI metrics from configured schedules.
- Full EPW/weather-file climate ray-traced simulation is not yet implemented.

## Reproducibility
- Debug bundle contains project snapshot, artifacts, and checksums.
- Reproduction assumes same solver/backend version unless explicitly cross-version validated.
