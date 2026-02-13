# AGI32 Parity Matrix

This matrix tracks functional parity against AGI32-style professional workflows.
Status labels:
- `Done`: implemented and covered by automated tests/gates.
- `Partial`: available but missing depth, standards coverage, or UX completeness.
- `Missing`: not implemented.

## Indoor (Core)

| Capability | Status | Notes |
|---|---|---|
| Project model (rooms, luminaires, assets, grids, jobs) | Done | Schema v5 + validation. |
| Direct illuminance workflow | Done | Path-based runner contract with persisted artifacts. |
| Radiosity workflow | Partial | Core engine available; advanced material/light transport parity needs deeper calibration. |
| UGR analysis | Partial | Engine + explicit views available; advanced glare standards coverage still expanding. |
| Determinism & hashing | Done | Determinism gates and manifest contract in place. |
| Indoor PDF/audit outputs | Done | `run-all` generates report + audit bundle. |

## Roadway

| Capability | Status | Notes |
|---|---|---|
| Roadway schema primitives (`RoadwaySpec`, `RoadwayGridSpec`) | Done | Includes layout and sampling linkage. |
| Roadway illuminance engine | Done | Dedicated `engine/road_illuminance.py`. |
| Roadway metrics + compliance proxy metrics | Partial | Core metrics implemented; standards-depth expansion remains. |
| Roadway report template (PDF) | Done | `export/templates/roadway_report.py` + `run-all` integration. |

## Geometry / Performance

| Capability | Status | Notes |
|---|---|---|
| Occlusion acceleration (BVH) | Done | Shared triangle BVH used by direct and glare visibility checks. |
| Performance regression guard | Partial | Benchmark + release gate script available; CI-hosted budget enforcement pending. |

## Agentic UX (Cursor-like)

| Capability | Status | Notes |
|---|---|---|
| Tool-only runtime execution | Done | Permission-tagged tool registry enforced in runtime path. |
| Structured runtime outputs (plan/diff/manifest/log) | Done | Typed session objects returned every run. |
| GUI Copilot sidebar with diff approvals | Done | Docked panel + per-change checkboxes + approval actions. |
| Multi-step workflow orchestration | Partial | Works for major flows; richer guided interactions and conflict resolution still expanding. |

## Optimization

| Capability | Status | Notes |
|---|---|---|
| Deterministic search loop with ranked candidates | Done | `optim/search.py` + artifacts. |
| Agent integration for optimize-and-apply flow | Done | `optim.search` tool + runtime wiring. |
| Advanced objective/cost models | Partial | Uses practical proxy objectives; full cost libraries not yet integrated. |

## Release Hardening

| Capability | Status | Notes |
|---|---|---|
| Gate tests (determinism, approvals, contracts, invariance) | Done | Present under `tests/gates/`. |
| Failure/recovery gate tests | Done | Missing-asset failure and no-artifact-on-failure gate. |
| Single-command release gates | Done | `scripts/release_gates.py` + `make release-check`. |
| Hosted CI workflow in repo | Partial | Local release gate runner exists; hosted CI config still to be added. |

## Current Release Goal

Near-term target is **production-grade parity for indoor + roadway + agentic workflows** with stable contracts and release gates, followed by standards-depth and enterprise CI packaging.
