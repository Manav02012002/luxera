# Indoor Workflow (AGi32-like Baseline)

## Supported End-to-End Flow
1. Define/import room geometry.
2. Add IES/LDT photometry assets.
3. Place luminaires (position + orientation).
4. Define workplane/grid.
5. Run direct illuminance job (`direct`, optional occlusion).
6. Compute stats + compliance summary.
7. Export client bundle + debug/audit bundle.

## Baseline Profile
- Profile: `office_en12464`
- Standard: `EN 12464-1:2021`
- Thresholds:
  - `avg_min_lux = 500`
  - `uniformity_min = 0.6`
  - `ugr_max = 19`

## Report Language Requirements
Reports must include:
- pass/fail status against chosen profile
- assumptions section
- unsupported-features section
- coordinate/units disclosure
- reproducibility metadata (hashes + versions)
