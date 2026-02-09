# UGR Contract

## Supported Variant
- Method: CIE 117 style UGR with explicit observer positions and view directions.
- Room context: indoor rectangular/workplace context.
- Output: per-view UGR values and worst-case aggregate.

## Assumptions
- Background luminance uses the implementation's room-average model.
- Luminaire luminance is approximated from photometry and luminous area.
- Observer views are represented by `glare_views` objects in project schema.

## Required Inputs
- Room geometry
- Luminaires with photometry + transforms
- Observer positions and view directions (`glare_views`)

## Output Contract
- Per-view tables: observer, view direction, UGR value.
- Worst-case UGR reported separately.
- Report must include assumptions and variant label.

## Validation Expectations
- Invariance checks for identical scenes under rigid translation.
- Monotonic trend checks with luminance increase.
