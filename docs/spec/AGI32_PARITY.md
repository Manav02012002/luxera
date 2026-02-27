# AGI32 Parity Matrix

This matrix tracks functional parity against AGI32-style professional workflows.
Status labels:
- `verified`: implemented and validated to release-claim standard.
- `not_supported`: not yet at release-claim standard.

## Indoor (Core)

| Capability | Status | Notes |
|---|---|---|
| Project model (rooms, luminaires, assets, grids, jobs) | verified | Schema v5 + validation. |
| Direct illuminance workflow | verified | Path-based runner contract with persisted artifacts. |
| Radiosity workflow | not_supported | Not yet validated for AGI32-grade parity claims. |
| UGR analysis | not_supported | Needs external parity validation and standards-depth completion. |
| Determinism & hashing | verified | Determinism gates and manifest contract in place. |
| Indoor PDF/audit outputs | verified | `run-all` generates report + audit bundle. |

## Roadway

| Capability | Status | Notes |
|---|---|---|
| Roadway schema primitives (`RoadwaySpec`, `RoadwayGridSpec`) | verified | Includes layout and sampling linkage. |
| Roadway illuminance engine | verified | Dedicated `engine/road_illuminance.py`. |
| Roadway metrics + compliance proxy metrics | not_supported | Standards-depth and glare completeness still pending. |
| Roadway report template (PDF) | verified | `export/templates/roadway_report.py` + `run-all` integration. |

## Geometry / Performance

| Capability | Status | Notes |
|---|---|---|
| Occlusion acceleration (BVH) | verified | Shared triangle BVH used by direct and glare visibility checks. |
| Performance regression guard | not_supported | Budget enforcement needs full production-scene coverage. |

## Agentic UX (Cursor-like)

| Capability | Status | Notes |
|---|---|---|
| Tool-only runtime execution | verified | Permission-tagged tool registry enforced in runtime path. |
| Structured runtime outputs (plan/diff/manifest/log) | verified | Typed session objects returned every run. |
| GUI Copilot sidebar with diff approvals | verified | Docked panel + per-change checkboxes + approval actions. |
| Multi-step workflow orchestration | not_supported | Needs robust guided interactions and conflict handling. |

## Optimization

| Capability | Status | Notes |
|---|---|---|
| Deterministic search loop with ranked candidates | verified | `optim/search.py` + artifacts. |
| Agent integration for optimize-and-apply flow | verified | `optim.search` tool + runtime wiring. |
| Advanced objective/cost models | not_supported | Full professional objective libraries still pending. |

## Release Hardening

| Capability | Status | Notes |
|---|---|---|
| Gate tests (determinism, approvals, contracts, invariance) | verified | Present under `tests/gates/`. |
| Failure/recovery gate tests | verified | Missing-asset failure and no-artifact-on-failure gate. |
| Single-command release gates | verified | `scripts/release_gates.py` + `make release-check`. |
| Hosted CI workflow in repo | verified | CI workflows committed under `.github/workflows/`. |

## Current Release Goal

Near-term target is **verified indoor direct parity + production desktop workflow**, with other domains explicitly kept `not_supported` until externally validated.
