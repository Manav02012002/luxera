# Feature Matrix

This matrix defines product scope and current implementation status.

Status labels:
- `verified`: implemented with automated tests in the repository and stable for release claims.
- `implemented`: implemented with tests present, but not yet externally benchmarked/validated for parity claims.
- `not_supported`: not available or not production-claim ready.

## Indoor Core

| Feature | Status | Notes |
|---|---|---|
| Project schema and validation | verified | Core schema + validator + runner contracts covered by tests. |
| Direct illuminance (grid, point sets, vertical planes) | verified | Deterministic direct solver and workflow tests. |
| Occlusion via BVH acceleration | verified | BVH tests and direct occlusion tests present. |
| Near-field warning detection | verified | Warning behavior covered by tests. |
| Near-field area source subdivision | verified | `tests/engine/test_near_field_area.py`. |
| Vectorised direct engine | verified | `tests/engine/test_vectorised.py`. |
| Multiprocessing direct engine path | verified | Parallel consistency covered in vectorised tests. |
| Cylindrical / semi-cylindrical illuminance | verified | `tests/engine/test_cylindrical_illuminance.py`. |

## Radiosity / Indirect

| Feature | Status | Notes |
|---|---|---|
| Classic radiosity solve loop | verified | Existing radiosity engine tests and workflows. |
| Hemicube form factors | verified | `tests/engine/test_hemicube.py`. |
| Spectral RGB radiosity | verified | `tests/engine/test_spectral_radiosity.py`. |
| Adaptive radiosity meshing | verified | `tests/engine/test_adaptive_mesh.py`. |

## Glare and Visual Comfort

| Feature | Status | Notes |
|---|---|---|
| Standard UGR workflow | verified | `tests/test_ugr_fidelity.py`, `tests/test_ugr_views.py`. |
| Advanced UGR (Guth index + shielding model) | verified | `tests/engine/test_advanced_ugr.py`. |

## Compliance and Standards

| Feature | Status | Notes |
|---|---|---|
| EN 12464 indoor compliance checks | verified | Compliance tests and runner integration. |
| CIE 171 validation scaffolding | implemented | Validation fixtures/tests exist; full external benchmark pending. |
| LENI / EN 15193 workflow | verified | `tests/compliance/test_leni.py`. |
| Maintenance factor decomposition | verified | MF decomposition tests and pipeline coverage present. |

## Outdoor and Specialty Domains

| Feature | Status | Notes |
|---|---|---|
| Exterior area lighting (EN 12464-2 classes) | verified | `tests/exterior/test_exterior.py`. |
| Facade / vertical exterior lighting | verified | `tests/exterior/test_exterior.py`. |
| Sports lighting EN 12193 | verified | `tests/sports/test_sports.py`. |
| Tunnel lighting CIE 88 workflow | implemented | Engine path exists with tests; external parity validation pending. |
| Roadway lighting workflow | verified | Roadway engine + metrics + profile tests. |
| Emergency lighting workflow | verified | Emergency engine/report tests present. |
| Daylight DF / annual proxy workflows | verified | Daylight tests and report export coverage present. |

## Visualization and Documentation

| Feature | Status | Notes |
|---|---|---|
| False-colour heatmaps and isolux plots | verified | `tests/viz/test_falsecolour.py`. |
| 3D false-colour room rendering | verified | `tests/viz/test_falsecolour.py`. |
| Polar candela plotting | verified | `tests/viz/test_falsecolour.py`. |
| Professional PDF report export | verified | Professional PDF and report tests present. |
| Layout plan export (SVG/PDF/DXF) | verified | `tests/export/test_layout_plan.py`. |

## Project Authoring and Data

| Feature | Status | Notes |
|---|---|---|
| Photometric library/search | verified | Library tests + API search endpoint tests. |
| Light scenes and dimming control groups | verified | Scene manager and runtime tests. |
| Design variant comparison and ranking | verified | `tests/results/test_comparison.py`. |
| Enhanced IFC import | verified | `tests/ifc/test_enhanced_import.py` and IFC suite. |
| Plugin system | verified | Plugin registry and CLI plugin integration tests. |

## Agent, API, and Automation

| Feature | Status | Notes |
|---|---|---|
| LLM planner/tool runtime | verified | Agent runtime tests. |
| Conversation memory | verified | Agent memory/context tests. |
| Compliance autopilot pipeline | verified | Pipeline and CLI/agent tests. |
| Batch pipeline | verified | `luxera.agent.batch` tests and CLI integration. |
| REST API workflow | verified | `tests/api/test_server.py` + integration API e2e. |
| Error diagnostics and typed error codes | verified | `tests/core/test_diagnostics.py`. |

## Integration Coverage

| Feature | Status | Notes |
|---|---|---|
| Indoor end-to-end workflow tests | implemented | `tests/integration/test_indoor_e2e.py`. |
| Outdoor end-to-end workflow tests | implemented | `tests/integration/test_outdoor_e2e.py`. |
| Agent end-to-end workflow tests | implemented | `tests/integration/test_agent_e2e.py`. |
| API end-to-end workflow tests | implemented | `tests/integration/test_api_e2e.py`. |
