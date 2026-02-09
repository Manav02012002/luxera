# Agent Contract

## Allowed Actions
- Propose/apply project diffs through tool APIs
- Import assets/geometry
- Add/update calc objects and jobs
- Run jobs (with explicit user approval)
- Generate reports and export bundles

## Forbidden Actions
- Fabricating numeric results
- Declaring compliance without executed job artifacts
- Silent changes to solver conventions/settings
- Direct file edits outside approved tool surface

## Required Interaction Pattern
1. Plan
2. Diff preview
3. Run manifest
4. Produced artifacts + assumptions/warnings
