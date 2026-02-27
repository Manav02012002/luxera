# Photometry Parsing

This document defines Luxera photometry parsing behavior for IES/LDT ingest, including edge-case handling and metadata propagation.

## Corpus

Reference edge cases live under `tests/photometry/corpus/`.

Included IES coverage:
- odd angle ordering (deterministic reordering)
- missing recommended keywords
- TILT variants (`NONE`, `INCLUDE`, `FILE` and missing file warning path)
- extreme candela magnitudes

## Parser Outputs

`parse_ies_text(...)` / `parse_ies_file(...)` return:
- photometric header, angle grid, candela table
- `metadata`:
  - `luminous_width_m`, `luminous_length_m`, `luminous_height_m`
  - `lumens`
  - `cct_k`, `cri`
  - `distribution_type`
  - `coordinate_system` (`Type A/B/C` mapping)
- `warnings` (structured, deterministic order)

Warning payload schema:
- `code`: stable machine key
- `message`: human-readable description
- `severity`: currently `warning`
- optional `line_no`
- optional `context`

## Deterministic Angle Handling

Luxera applies strict-but-tolerant normalization:
- vertical/horizontal angle lists are sorted ascending when needed
- candela table is reordered to keep data aligned with sorted angle axes
- duplicate angles are collapsed deterministically by mean aggregation on the affected axis
- Type C horizontal angles are normalized to `[0, 360)` (`360` merged onto seam `0`)

Structured warnings emitted when normalization is applied:
- `vertical_angles_reordered`
- `horizontal_angles_reordered`
- `vertical_angles_deduplicated`
- `horizontal_angles_deduplicated`
- `horizontal_angles_wrapped` (Type C wrap normalization)

Hard validation remains for truly invalid payloads:
- Type C horizontal axis lacking `0°` after wrap normalization
- malformed numeric blocks / count mismatches

## Luminous Dimensions + Proxy Consumers

Luminous opening dimensions are normalized to meters at ingest.

For IES:
- dimensions use LM-63 `units_type`
- feet are converted to meters (`0.3048`)

Consumers wired to these dimensions:
- UGR luminaire apparent area (`width * length`)
- Radiance rectangle proxy emitter geometry

If dimensions are missing/non-positive, existing conservative defaults are used.

## Result Surface

Runtime `result.json` includes:
- `photometry_assets.<asset_id>.metadata`
- `photometry_assets.<asset_id>.warnings[]`
- aggregated `photometry_warnings[]` with `asset_id` for CI/report processing
- aggregated `near_field_warnings[]` with luminaire + grid context
- combined `warnings[]` (photometry parser warnings + near-field warnings)

No parser `print()` warnings are used; warnings are structured artifacts.

## Near-Field Heuristic Warnings

Luxera emits a deterministic near-field risk warning when:

- `min_distance(calc_points, luminaire_position) < k * max(luminous_width, luminous_length, luminous_height)`
- default `k = 5.0`
- if dimensions are unavailable, fallback reference dimension is `0.6 m`

Warning payload includes:
- `code=near_field_photometry_risk`
- `luminaire_id`
- `photometry_asset_id`
- `affected_grids`
- `min_distance_m`
- `threshold_m`
- mitigation text

Reports include an appendix section titled `Photometry Warnings` that renders these structured warnings.

## Symmetry Expansion + Seam Handling

For LM-63 Type C files that provide partial C-planes:
- `0..90` (quadrant), `0..180` (bilateral), or single-plane (`FULL`) inputs are expanded to a canonical full `0..360` C-plane representation in `photometry_from_parsed_ies(...)`.
- expansion is deterministic and mirror-based; no stochastic interpolation is used for expansion itself.
- seam handling uses cyclic interpolation between the last C-plane and `0°`, avoiding discontinuities at `0/360`.

This keeps sampling stable across irregular C-plane spacing and wrap-around stress cases.
