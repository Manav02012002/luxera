# AGI32 Parity Matrix

This matrix tracks Luxera capability parity against AGI32-style professional workflows.

Status labels:
- `verified`: implemented and covered by automated tests in this repository.
- `implemented`: implemented and test-covered, but full external parity benchmarking is still pending.
- `not_supported`: capability absent or not yet claim-ready.

## Core Calculation Parity

| Capability | Status | Notes |
|---|---|---|
| Direct illuminance workflow | verified | Core runner + validation suites. |
| Hemicube form factors | verified | `tests/engine/test_hemicube.py`. |
| Spectral RGB radiosity | verified | `tests/engine/test_spectral_radiosity.py`. |
| Near-field area sources | verified | `tests/engine/test_near_field_area.py`. |
| Adaptive radiosity meshing | verified | `tests/engine/test_adaptive_mesh.py`. |
| Vectorised engine | verified | `tests/engine/test_vectorised.py`. |
| Advanced UGR | verified | `tests/engine/test_advanced_ugr.py`. |
| Standard UGR set evaluation | verified | `tests/test_ugr_fidelity.py`, `tests/test_ugr_views.py`. |

## Compliance and Standards Parity

| Capability | Status | Notes |
|---|---|---|
| EN 12464-1 indoor checks | verified | Compliance tests + runner integration. |
| CIE 171 validation | implemented | Reference scaffolding + fixtures; external benchmark set still expanding. |
| Cylindrical/semi-cylindrical illuminance | verified | `tests/engine/test_cylindrical_illuminance.py`. |
| LENI / EN 15193 | verified | `tests/compliance/test_leni.py`. |
| Maintenance factor decomposition | verified | MF decomposition tests and compliance path coverage. |
| Exterior area/facade lighting | verified | `tests/exterior/test_exterior.py`. |
| Sports lighting EN 12193 | verified | `tests/sports/test_sports.py`. |
| Tunnel lighting CIE 88 | implemented | Workflow in place; broad external parity validation pending. |

## Visualisation and Documentation Parity

| Capability | Status | Notes |
|---|---|---|
| False-colour visualisation | verified | `tests/viz/test_falsecolour.py`. |
| Isolux contour generation | verified | Covered in false-colour test suite. |
| Professional PDF reports | verified | Report/export tests and production builder path. |
| Layout plan export (DXF/SVG/PDF) | verified | `tests/export/test_layout_plan.py`. |
| Photometric appendix / polar plots | verified | Polar render tests in viz suite. |

## Platform and Workflow Parity

| Capability | Status | Notes |
|---|---|---|
| Light scenes and dimming | verified | Scene manager + workflow tests. |
| Photometric library | verified | Library + API search tests. |
| LLM planner | verified | Planner/runtime tooling tests. |
| Conversation memory | verified | Agent context persistence tests. |
| Compliance pipeline | verified | Agent pipeline tests and CLI flows. |
| REST API | verified | `tests/api/test_server.py` + integration e2e. |
| Plugin system | verified | Plugin registry/load tests. |
| Enhanced IFC import | verified | `tests/ifc/test_enhanced_import.py`. |
| Batch pipeline | verified | Agent batch tests + CLI batch e2e. |
| Design variant comparison | verified | `tests/results/test_comparison.py`. |
| Error diagnostics | verified | `tests/core/test_diagnostics.py`. |

## Current Parity Position

Luxera now has broad feature-level implementation coverage across prompts 1-43, with strong automated test coverage for most capabilities.

Remaining gaps to AGI32-grade parity claims are primarily:
- external benchmark correlation/validation depth for some advanced domains,
- comprehensive real-project performance benchmarking across large production scenes,
- certification-grade standards validation packages for all non-indoor workflows.
