# Roadway Glare

This document defines disability glare metrics for roadway jobs.

## Implemented Pipeline

For each observer viewpoint and each luminaire:

1. Compute geometry from observer to luminaire:
   - distance `d`
   - off-axis angle `theta` from observer view direction (default `+X` roadway direction)
2. Sample luminaire intensity toward observer from IES/LDT photometry: `I` (cd)
3. Compute eye illuminance proxy:
   - `E_eye = I / d^2`
4. Compute veiling luminance contribution using RP-8 style form:
   - `Lv_i = K * E_eye / theta^2`
   - default `K = 10`
   - `theta` clamped to configured bounds (`glare_theta_min_deg`, `glare_theta_max_deg`)

Total veiling luminance per observer:

- `Lv_total = sum_i Lv_i`

## Glare Metrics

Supported selected methods:

- `rp8_veiling_ratio` (default)
  - `rp8_veiling_ratio = Lv_total / Lavg_ref`
  - `Lavg_ref` is roadway mean luminance (`road_luminance_mean_cd_m2`)
- `ti_proxy_percent` (optional proxy)
  - `ti_proxy_percent = 100 * rp8_veiling_ratio`
- `ti_cie` / `ti`
  - `ti_percent = 65 * Lv_total / (Lavg_ref ^ 0.8)`
  - `Lavg_ref` is roadway mean luminance (`road_luminance_mean_cd_m2`)

`ti_percent` is an engineering TI approximation from veiling luminance and adaptation luminance; it is deterministic but does not include every standard-specific correction term.

## Outputs

Roadway summary includes:

- `observer_glare_views[]`
  - per-observer glare row with per-luminaire contributions
- `worst_case_glare`
  - selected method, worst observer, worst metric value
- `rp8_veiling_ratio_worst`
- `threshold_increment_ti_proxy_percent` (set from worst `ti_proxy_percent`)
- `threshold_increment_ti_percent` (set from worst `ti_percent`)

## Reporting

Roadway reports render:

- per-observer glare table
- worst-case glare summary table

## Stability

- deterministic observer ordering inherited from roadway observer resolution
- finite-domain guards on distance/intensity/angle
- angle clamping prevents singularities near line of sight
