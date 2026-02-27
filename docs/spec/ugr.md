# UGR Engine Specification

This document defines Luxera's UGR computation behavior.

## Formula

Luxera computes UGR per observer using the CIE-117 style form:

`UGR = 8 * log10( (0.25 / Lb) * sum( L^2 * omega / p^2 ) )`

- `Lb`: background luminance (cd/m2)
- `L`: luminaire luminance estimate in observer direction (cd/m2)
- `omega`: apparent solid angle of luminous opening (sr)
- `p`: Guth-style position index

Implementation equation:

`log_term = (0.25 / max(Lb, 1e-9)) * sum(L^2 * omega / p^2)`

`UGR = 0                              if log_term <= 0`

`UGR = 8 * log10(max(log_term, 1e-12)) otherwise`

Final UGR is clamped to `[0, 40]`.

## Apparent Geometry and Luminance

For each luminaire/observer pair:

1. Direction from observer to luminaire is formed.
2. Apparent luminous area is estimated from luminous opening area and orientation:
   - `A_app = A_luminous * max(0, dot(n_lum, dir_lum_to_observer))`
3. Apparent solid angle is approximated by:
   - `omega = clamp(A_app / d^2, 0, 2*pi)`
4. Directional intensity is sampled from photometry in the observer direction.
5. Luminance estimate:
   - `L = I(direction) / max(A_app, eps)`

This uses luminous dimensions directly and does not implement near-field source modeling.

## View-Set Handling

For each observer view:

- Luminaires behind observer are excluded using full 3D view test:
  - `dot(dir_observer_to_luminaire, view_direction) <= 1e-9` => excluded
- Horizontal and vertical off-axis angles are computed in an observer-centric orthonormal frame.
- A simplified Guth-style position index is used consistently.

## Position Index Method

Luxera currently uses the implemented simplified Guth-style function in
`calculate_guth_position_index(H, T)` for stability and monotonic behavior.
This is the authoritative method used by both default-grid and explicit-view UGR paths.

## Debug Mode

Debug mode is enabled by `ugr_debug_top_n > 0` (radiosity job settings).

Runner writes `summary.ugr_debug` for the maximum UGR point/view across all evaluated observer sets (default grid and/or explicit views):

- `mode`: `default_grid` or `explicit_views`
- `observer`: observer label
- `max_ugr`: UGR value at that worst point/view
- `top_n`: requested contributor count
- `top_contributors`: sorted descending by contribution (stable tie-break by `luminaire_id`)

Contributor fields (stable contract):

- `luminaire_id`
- `omega`
- `luminance_est`
- `position_index`
- `contribution`

## Reporting

- Report always includes a UGR summary table when UGR results exist.
- Debug appendix section is controlled by radiosity job setting:
  - `ugr_debug_appendix: true` => include `UGR Debug Appendix`
  - default is `false`.
