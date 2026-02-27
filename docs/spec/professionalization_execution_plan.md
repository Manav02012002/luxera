# Professionalization Execution Plan

This is the implementation board for AGI32-grade professionalization under the no-scaffold policy.

## Rules

1. No placeholders, no TBD references, no stubbed feature claims.
2. Feature claims are binary: `verified` or `not_supported`.
3. External provenance is mandatory for parity references.
4. UI controls are exposed only for implemented and validated behavior.

## Milestone M0: Quality Lock

### Scope

1. Enforce no-scaffold guard in CI and release gates.
2. Normalize feature and parity state taxonomy.
3. Publish implementation backlog with concrete acceptance criteria.

### Acceptance Criteria

1. `scripts/no_scaffold_guard.py` passes in CI.
2. `tests/gates/test_no_scaffold_policy.py` passes.
3. `docs/spec/feature_matrix.md` and `docs/spec/AGI32_PARITY.md` use only `verified` / `not_supported`.

## Milestone M1: Indoor Direct AGI32 Parity

### Scope

1. Build external-reference corpus for indoor direct workflows.
2. Validate direct solver against AGI32/DIALux/manual calculations.
3. Lock tolerances and publish parity report artifacts.

### Acceptance Criteria

1. At least 30 externally referenced indoor direct cases, each with provenance.
2. Mean/pointwise metrics pass agreed tolerances by case class.
3. Determinism gates and performance budgets pass on representative scenes.
4. Desktop app can run indoor direct jobs and inspect result grids end-to-end.

## Milestone M2: UGR Parity

### Scope

1. Observer/view workflow parity with professional use patterns.
2. External-reference validation corpus for UGR.

### Acceptance Criteria

1. UGR results match reference tools within declared tolerances.
2. UGR workflow is fully operable in desktop UI.

## Milestone M3: Radiosity Professionalization

### Scope

1. Interreflection fidelity and convergence robustness.
2. Canonical validation vs reference transport tools.

### Acceptance Criteria

1. Stable convergence and energy accounting on canonical scenes.
2. External-reference comparisons documented and passing.

## Milestone M4: Roadway, Daylight, Emergency

### Scope

1. Roadway glare completeness.
2. Daylight and emergency reference suites without placeholder metrics.

### Acceptance Criteria

1. No placeholder metrics/cases in released validation suites.
2. Each domain reaches externally validated `verified` state before claim.
