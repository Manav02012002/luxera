# Luxera

Luxera is a cross-platform, open-source lighting calculation and analysis tool. It provides photometric parsing, direct and interreflected illuminance computation, glare evaluation, compliance checking, geometry import/export, PDF reporting, and an interactive desktop GUI -- all built on a pure Python core with no OS-specific dependencies.

Version: 0.2.0
Status: Active development
Platforms: macOS, Linux, Windows
Python: 3.11+
License: TBD (recommended MIT or Apache-2.0)


## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Module Reference](#module-reference)
- [Installation](#installation)
- [CLI Reference](#cli-reference)
- [Project File Format](#project-file-format)
- [Calculation Engines](#calculation-engines)
- [Geometry Pipeline](#geometry-pipeline)
- [Photometry](#photometry)
- [Compliance and Standards](#compliance-and-standards)
- [Reporting and Export](#reporting-and-export)
- [Interactive GUI](#interactive-gui)
- [Agentic AI Runtime](#agentic-ai-runtime)
- [Optimization](#optimization)
- [Radiance Backend](#radiance-backend)
- [Testing](#testing)
- [Examples](#examples)
- [Design Principles](#design-principles)
- [Specifications and Contracts](#specifications-and-contracts)


## Overview

Luxera is structured as a computation-first lighting tool. The core library handles parsing, validation, calculation, and export without requiring a GUI. The desktop interface (PySide6) and the agentic AI assistant are thin layers on top of the same engine, which means every operation available in the GUI is also available via the CLI or the Python API.

Supported calculation types:

- Direct illuminance (point-by-point, with BVH-accelerated shadow casting)
- Full radiosity (Jacobi iteration with Monte Carlo or analytic form factors)
- Unified Glare Rating (CIE 117:1995, with configurable observer positions)
- Daylight factor and annual daylight proxy metrics (DA, sDA, UDI)
- Roadway illuminance and observer-view luminance
- Emergency lighting with battery decay modelling

Supported standards:

- EN 12464-1:2021 (indoor workplace lighting)
- EN 13032 (photometric data presentation)
- CIE 117:1995 (UGR)
- IES LM-63 (IES photometric file format)
- EULUMDAT (European photometric file format)
- IES RP-8 / CIE 115 (roadway lighting, partial)


## Architecture

```
luxera/
|-- parser/          IES (LM-63) and EULUMDAT (.ldt) parsing, tilt files
|-- photometry/      Canonical photometric model, interpolation, sampling, verification
|-- cache/           Photometric interpolation LUT caching (content-addressed .npz)
|-- core/            Coordinate systems, transforms, hashing, unit conversions
|-- geometry/        Polygons, surfaces, rooms, materials, BVH, CSG, curves,
|                    parametric models, mesh cleaning, topology, views, openings
|-- calcs/           Adaptive grid refinement, geometry-aware masks, obstacle handling
|-- calculation/     Illuminance kernel, radiosity primitives, UGR formula, grid plots
|-- engine/          High-level engine drivers:
|   |-- direct_illuminance    Point-by-point with occlusion
|   |-- radiosity/            Form factors + Jacobi solver
|   |-- radiosity_engine      Project-level radiosity orchestration
|   |-- ugr_engine            UGR with configurable observer sets
|   |-- road_illuminance      Roadway grid illuminance
|   |-- road_luminance        Observer-view road luminance
|   |-- daylight_df           Daylight factor
|   |-- daylight_radiance     Daylight via Radiance backend
|   |-- daylight_annual_radiance  Annual daylight metrics
|   |-- emergency_escape_route    Escape route illuminance with battery decay
|   |-- emergency_open_area       Open area emergency illuminance
|-- backends/        External solver adapters (Radiance rtrace/oconv)
|-- project/         Project schema (v5), I/O, migrations, validation, diff,
|                    history (undo/redo), presets, variants, runner
|-- results/         Result storage, CSV/JSON writers, heatmaps, isolux, surface grids
|-- compliance/      EN 12464-1 requirement database, compliance checking, emergency standards
|-- metrics/         Basic illuminance statistics, standards-specific derived metrics
|-- derived/         Summary tables, worst-case extraction
|-- validation/      Rule-based IES file validation engine
|-- io/              DXF import/export, IFC import/export, OBJ/GLTF/FBX/SKP mesh import
|-- scene/           Scene graph construction from project data
|-- design/          Luminaire placement helpers (rectangular arrays, line arrays, ceiling snap)
|-- optim/           Deterministic layout search, optimizer with ranked candidates
|-- export/          PDF reports (EN 12464, EN 13032, roadway, emergency, daylight),
|                    client bundles, debug bundles, backend comparison HTML
|-- plotting/        Matplotlib intensity curves, polar plots
|-- viz/             False-colour illuminance/luminance rendering
|-- database/        Luminaire catalog management
|-- gui/             PySide6 desktop application (workspace, widgets, 3D/2D viewports,
|                    copilot panel, inspector, job manager, project tree)
|-- viewer/          OpenGL 3D renderer (camera, shaders, mesh, streaming, demo)
|-- agent/           Agentic AI runtime, tool registry, audit log, skills, context,
|                    session management, structured plan/diff/manifest types
|-- ai/              Layout proposal engine, assistant helpers
|-- ops/             Transactional scene operations with undo/redo
|-- outdoor/         Outdoor site geometry
|-- road/            Roadway-specific calculation primitives
|-- emergency/       Emergency lighting workflow orchestration
|-- daylight/        Daylight workflow orchestration
|-- reporting/       Report model construction and schedule auditing
|-- testing/         Test utilities and fixtures
|-- legacy/          Deprecated code kept for migration reference
|-- cli.py           Unified command-line interface
|-- runner.py        Convenience wrapper for project job execution
```

Total: approximately 42,000 lines of Python across 295 source files.


## Module Reference

### Core Modules

| Module | Lines | Description |
|--------|-------|-------------|
| `geometry/` | 7,528 | CSG operations, BVH acceleration, mesh cleaning, curves, parametric models, polygon operations, surface topology, view projections, opening subtraction |
| `project/` | 4,099 | Project schema (v5) with typed dataclasses, JSON I/O with schema migrations (v1-v5), project validation, diff engine, undo/redo history, variant management, presets, job runner |
| `gui/` | 3,780 | PySide6 desktop application with workspace layout, project tree, inspector, job manager, results viewer, 3D/2D viewports, copilot panel, assistant panel, theme support |
| `io/` | 3,178 | DXF import/export (with roundtrip bulge arc support), IFC import/export (with IfcSpace-to-room derivation, opening subtraction, axis metadata), OBJ/GLTF/FBX/SKP mesh import |
| `viewer/` | 2,473 | OpenGL 3D renderer with orbit/pan/zoom camera, Phong and flat shading, grid overlay, storey-based streaming for large models |
| `agent/` | 2,315 | Agentic AI runtime with permission-tagged tool registry, structured plan/diff/manifest outputs, audit logging, session persistence, skills system |
| `engine/` | 2,234 | Calculation engine drivers for direct illuminance, radiosity, UGR, roadway, daylight, and emergency workflows |
| `calculation/` | 2,114 | Low-level illuminance kernel (inverse-square cosine law with photometric lookup), radiosity BVH and form factor primitives, UGR formula implementation |
| `export/` | 1,826 | PDF report generation (ReportLab), HTML reports, client delivery bundles (ZIP), debug/audit bundles, backend comparison exports |
| `ops/` | 1,717 | Transactional scene operations: add/remove/modify rooms, luminaires, grids, surfaces with grouped undo/redo and rebuild replay |

### Supporting Modules

| Module | Lines | Description |
|--------|-------|-------------|
| `parser/` | 859 | IES LM-63 parser (strict, line-aware error reporting), EULUMDAT (.ldt) parser, tilt file loader, analysis pipeline |
| `compliance/` | 842 | EN 12464-1:2021 requirement database (30+ activity types), compliance checking with pass/fail/warning, emergency lighting standards |
| `photometry/` | 821 | Canonical photometric model (Type C/B/A coordinate systems), bilinear interpolation, intensity sampling, format verification |
| `results/` | 553 | Result directory management, CSV/JSON writers, surface heatmap generation, grid heatmap and isolux contour rendering |
| `optim/` | 458 | Deterministic layout search over candidate grids, multi-objective ranking (illuminance, uniformity, UGR, energy), optimizer with artifact output |
| `scene/` | 406 | Scene graph construction from project schema, node binding, transform propagation |
| `validation/` | 532 | Rule-based IES file validation with error/warning/info classification, extensible rule registry |
| `calcs/` | 517 | Adaptive grid refinement, geometry-aware sample masking (obstacles, openings, no-go zones) |
| `backends/` | 514 | Radiance adapter (oconv, rtrace), roadway Radiance pipeline, tool detection, manifest generation |
| `design/` | 305 | Rectangular and linear luminaire array placement, ceiling snap, grid intersection snap |
| `daylight/` | 292 | Daylight factor and annual daylight workflow orchestration |
| `database/` | 290 | Luminaire catalog (JSON-backed), IES-to-catalog import, search by metadata |


## Installation

### Development Setup

```bash
# Create environment (conda or venv)
conda create -n luxera python=3.11
conda activate luxera

# Install in editable mode with core dependencies
pip install -e .

# Install GUI dependencies (optional)
pip install pyside6

# Install dev dependencies
pip install pytest
```

### Dependencies

Core (installed automatically via `pip install -e .`):

- numpy >= 2.4
- matplotlib >= 3.10
- pillow >= 12
- pydantic >= 2.12
- reportlab >= 4.0

Optional:

- PySide6 >= 6.7 (GUI)
- Radiance (oconv, rtrace) for Radiance backend workflows
- trimesh (for GLTF/FBX/SKP mesh import)


## CLI Reference

All commands are invoked via `python -m luxera.cli <command>`.

### IES Inspection

```bash
# Generate a demo IES file
python -m luxera.cli demo --out data/demo.ies

# Parse, plot, and optionally generate a PDF report
python -m luxera.cli view path/to/file.ies --out out/ --stem myfile
python -m luxera.cli view path/to/file.ies --out out/ --stem myfile --pdf

# Verify photometry file conventions and hash
python -m luxera.cli photometry verify path/to/file.ies
```

### Project Management

```bash
# Initialize a new project
python -m luxera.cli init --name "My Project" --out project.luxera.json

# Add a photometry asset
python -m luxera.cli add-photometry project.luxera.json path/to/fixture.ies

# Add a room
python -m luxera.cli add-room project.luxera.json \
    --name "Office" --width 6 --length 8 --height 2.8 \
    --floor-refl 0.2 --wall-refl 0.5 --ceil-refl 0.7 \
    --activity OFFICE_GENERAL

# Add a luminaire instance
python -m luxera.cli add-luminaire project.luxera.json \
    --asset-id <asset_id> --name "Panel A" \
    --x 1.5 --y 2.0 --z 2.8 --yaw 0 --pitch 0 --roll 0

# Add a calculation grid
python -m luxera.cli add-grid project.luxera.json \
    --name "Workplane" --width 6 --height 8 \
    --elevation 0.8 --nx 25 --ny 33

# Add a calculation job
python -m luxera.cli add-job project.luxera.json \
    --type direct --id office_direct

# Add compliance profile presets
python -m luxera.cli add-profile-presets project.luxera.json
```

### Calculation

```bash
# Run a single job
python -m luxera.cli run project.luxera.json --job office_direct

# Run all: validate, calculate, generate report and audit bundle
python -m luxera.cli run-all project.luxera.json \
    --job office_direct --report --bundle

# Run a daylight job
python -m luxera.cli daylight project.luxera.json --job daylight_df
```

### Geometry Import

```bash
# Import geometry from DXF, IFC, OBJ, GLTF, FBX, or SKP
python -m luxera.cli geometry import project.luxera.json path/to/model.ifc

# Clean imported geometry (fix normals, merge coplanar, detect rooms)
python -m luxera.cli geometry clean project.luxera.json --detect-rooms
```

### Export and Reporting

```bash
# Export PDF compliance report
python -m luxera.cli export-debug project.luxera.json --job office_direct

# Export client delivery bundle
python -m luxera.cli export-client project.luxera.json --job office_direct

# Export roadway report
python -m luxera.cli export-roadway-report project.luxera.json --job road_direct

# Compare two job results
python -m luxera.cli compare-results project.luxera.json \
    --job-a office_direct --job-b office_radiosity

# Compare design variants
python -m luxera.cli compare-variants project.luxera.json \
    --job office_direct --variants v1 v2 v3
```

### Golden Regression

```bash
# Run golden test case
python -m luxera.cli golden run --case indoor_office

# Compare against expected
python -m luxera.cli golden compare --case indoor_office

# Update expected artifacts
python -m luxera.cli golden update --case indoor_office
```

### GUI

```bash
python -m luxera.cli gui
```


## Project File Format

Luxera uses a JSON project file (`.luxera.json`) at schema version 5. The schema is defined in `luxera/project/schema.py` as a hierarchy of frozen dataclasses.

### Top-Level Structure

```
Project
|-- name, schema_version (5)
|-- geometry: Geometry
|   |-- rooms: [RoomSpec]
|   |-- zones: [ZoneSpec]
|   |-- no_go_zones: [NoGoZoneSpec]
|   |-- surfaces: [SurfaceSpec]
|   |-- openings: [OpeningSpec]
|   |-- obstructions: [ObstructionSpec]
|   |-- levels: [LevelSpec]
|   |-- coordinate_systems: [CoordinateSystemSpec]
|   |-- length_unit, scale_to_meters
|-- materials: [MaterialSpec]
|-- material_library: [MaterialLibraryEntry]
|-- photometry_assets: [PhotometryAsset]
|-- luminaire_families: [LuminaireFamily]
|-- luminaires: [LuminaireInstance]
|-- grids: [CalcGrid]
|-- workplanes, vertical_planes, point_sets, line_grids, arbitrary_planes
|-- jobs: [JobSpec]
|-- results: [JobResultRef]
|-- compliance_profiles: [ComplianceProfile]
|-- escape_routes, emergency, daylight, roadway specs
|-- variants: [VariantSpec]
|-- layers, symbols_2d, block_instances, selection_sets
|-- agent_history, assistant_undo_stack, assistant_redo_stack
```

### Job Types

| Type | Backend | Description |
|------|---------|-------------|
| `direct` | `cpu` | Point-by-point direct illuminance with optional BVH occlusion |
| `direct` | `radiance` | Direct illuminance via Radiance rtrace |
| `radiosity` | `cpu` | Full interreflected illuminance (Jacobi solver) |
| `roadway` | `cpu` | Roadway grid illuminance and observer-view luminance |
| `emergency` | `cpu` | Emergency lighting with battery decay |
| `daylight` | `df` | Daylight factor |
| `daylight` | `radiance` | Annual daylight metrics via Radiance |

### Schema Migrations

The project I/O layer (`luxera/project/io.py`) includes automatic migration from schema v1 through v5. Older project files are upgraded transparently on load.

### Result Persistence

Job results are stored under `.luxera/results/<job_hash>/` relative to the project file. Each result directory contains:

- `manifest.json` -- deterministic job hash, input checksums, engine version, timing
- `grid.csv` -- per-point illuminance values
- `summary.json` -- aggregate metrics (Eavg, Emin, Emax, U0, U1, UGR)
- `heatmap.png` -- false-colour illuminance map
- `isolux.png` -- isolux contour plot
- `report.pdf` -- compliance report (when requested)

The job hash is computed from project inputs (geometry, photometry content hashes, grid specs, job settings, seed) ensuring deterministic, content-addressed result storage.


## Calculation Engines

### Direct Illuminance

The direct illuminance engine (`engine/direct_illuminance.py`) computes point-by-point illuminance from the inverse-square cosine law using photometric intensity lookups:

```
E = (I(C, gamma) / d^2) * cos(theta) * MF
```

where I(C, gamma) is the luminous intensity at horizontal angle C and vertical angle gamma, d is the distance from luminaire to calculation point, theta is the angle of incidence, and MF is the maintenance factor.

Shadow casting uses a two-level BVH (TLAS/BLAS) acceleration structure built over triangulated scene surfaces. Ray-triangle intersection tests determine binary occlusion (hard shadows).

Supported calculation surface types:

- Horizontal grids (workplane illuminance)
- Vertical planes (wall illuminance, with azimuth orientation)
- Arbitrary oriented planes
- Point sets (scattered calculation points)
- Line grids (polyline-sampled calculation points)

### Radiosity

The radiosity engine (`engine/radiosity/`) implements Jacobi iteration over a patch-based radiosity system:

1. Scene surfaces are subdivided into patches based on a configurable maximum patch area
2. Form factors are computed between all patch pairs using either analytic (point-to-point) or Monte Carlo methods, with optional BVH visibility testing
3. The system iterates B_next = E + rho * (F @ B) with configurable damping, convergence tolerance, and maximum iterations
4. Energy conservation is enforced by normalising form factor row sums
5. Convergence monitoring includes energy blow-up detection and residual tracking

The solver returns per-patch radiosity, irradiance, form factor matrix, convergence status, and energy accounting.

### UGR

The UGR engine (`engine/ugr_engine.py`, `calculation/ugr.py`) implements the CIE 117:1995 Unified Glare Rating formula:

```
UGR = 8 * log10 [ (0.25 / Lb) * sum(L^2 * omega / p^2) ]
```

UGR is computed for configurable observer positions (default: seated at 1.2m and standing at 1.7m eye height) looking along room axes. Background luminance is derived from room surface reflectances and the radiosity/direct illuminance solution. Luminaire luminance is sampled from the photometric distribution in the observer's viewing direction.

### Roadway

The roadway engine (`engine/road_illuminance.py`, `engine/road_luminance.py`) computes:

- Point-by-point illuminance on roadway grids defined per IES RP-8 conventions
- Observer-view luminance using a Lambertian road surface model
- Grid layout follows lane-based definitions with configurable offsets

### Daylight

The daylight engine supports:

- Daylight factor (ratio of indoor to outdoor illuminance under CIE overcast sky)
- Annual daylight metrics (DA, sDA, UDI) via proxy scheduling or Radiance backend

### Emergency

The emergency engine models:

- Escape route illuminance along polyline paths
- Open area illuminance
- Battery decay (linear or exponential) over configurable duration


## Geometry Pipeline

### Import Formats

| Format | Module | Notes |
|--------|--------|-------|
| DXF | `io/dxf_import.py` | 2D/3D entities, block inserts, layer mapping, room extraction from closed polylines |
| IFC | `io/ifc_import.py` | IfcSpace to room derivation, opening subtraction, wall/slab/roof surface extraction, level detection, axis convention handling |
| OBJ | `io/mesh_import.py` | Wavefront OBJ with face parsing |
| GLTF/GLB | `io/mesh_import.py` | Via trimesh (when available) or extras fallback |
| FBX | `io/mesh_import.py` | Via trimesh |
| SKP | `io/mesh_import.py` | Via trimesh |
| DWG | `io/geometry_import.py` | Requires external conversion to DXF/IFC/OBJ |

### Export Formats

| Format | Module | Notes |
|--------|--------|-------|
| DXF | `io/dxf_export.py`, `io/dxf_export_pro.py` | Layer-separated output with luminaire symbols, grid points, isolux contours, bulge arc roundtrip |
| IFC | `io/ifc_export.py` | IfcSpace export with material assignments |

### Geometry Core

The geometry module provides:

- `Polygon` and `Surface` primitives with area, normal, centroid, and subdivision
- `Room` construction (rectangular rooms with floor/wall/ceiling surfaces and materials)
- `Material` model with broadband scalar reflectance, optional RGB, specularity, transmittance
- BVH acceleration for ray-triangle intersection (single-level and two-level TLAS/BLAS)
- CSG operations (union, difference, intersection via mesh boolean)
- Curve primitives (arcs, polylines, polycurves) with offset, intersection, and trim/extend
- Parametric models with dependency graph and rebuild pipeline
- Mesh cleaning (degenerate triangle removal, vertex merging, winding repair, normal consistency)
- Polygon2D operations (validation, hole handling, doctor/repair)
- Surface topology (adjacency detection, shared wall identification)
- View projection (plan views, hidden line removal, cutplane sections)
- Opening subtraction (UV-projected opening polygons cut from wall surfaces, with triangulation)
- LOD (level of detail) with bounds-preserving simplification

### Unit Handling

Luxera supports m, mm, cm, ft, and in as length units. The project schema stores a `length_unit` and `scale_to_meters` factor. All internal calculations operate in metres. Import pipelines detect source units and apply conversion automatically.

### Coordinate Conventions

The internal coordinate system is Z-up, right-handed. Import pipelines apply axis conversions as needed (documented in `docs/spec/coordinate_conventions.md`). The applied transform is recorded in the project geometry metadata.


## Photometry

### Parsing

The IES parser (`parser/ies_parser.py`) implements strict LM-63 parsing with:

- Standard header recognition (IESNA:LM-63-1995, IESNA:LM-63-2002)
- Keyword block extraction ([MANUFAC], [LUMCAT], [TEST], etc.)
- Photometric geometry (Type C/B/A coordinate systems)
- Vertical and horizontal angle grids with validation
- Candela distribution matrix
- Line-aware error reporting with informative messages

The EULUMDAT parser (`parser/ldt_parser.py`) implements the fixed-line-position EULUMDAT format with:

- Symmetry indicator handling (0-4)
- C-plane and gamma angle grid extraction
- Luminous area dimensions
- Downward flux fraction
- Conversion to the internal photometric model

### Tilt Files

The tilt file loader (`parser/tilt_file.py`) reads TILT=INCLUDE data and standalone tilt files, providing angle-dependent lamp multiplier curves.

### Canonical Model

All photometric data is normalised to a canonical representation (`photometry/canonical.py`) with:

- Coordinate system label (C, B, or A)
- Uniform angle grids (horizontal and vertical)
- 2D intensity matrix (cd)
- Content hash for deterministic caching and result reproducibility

### Interpolation

Bilinear interpolation over the canonical angle grid provides intensity values at arbitrary directions. Interpolation LUTs are cached to disk (content-addressed `.npz` files under `.luxera/cache/photometry/`) for runtime acceleration.

### Verification

The photometry verifier (`photometry/verify.py`) checks:

- File format correctness
- Angle grid monotonicity and coverage
- Candela distribution sanity (non-negative, finite)
- Total flux consistency
- Content hash computation


## Compliance and Standards

### EN 12464-1:2021

The compliance module (`compliance/standards.py`) contains a database of lighting requirements for 30+ activity types spanning offices, industrial spaces, retail, education, healthcare, circulation areas, amenity spaces, and parking. Each entry specifies:

- Maintained illuminance (Em, lux)
- Uniformity ratio (Uo = Emin/Eavg)
- UGR limit
- Minimum CRI
- Optional CCT range

The `check_compliance()` function compares calculated values against the standard and produces a `ComplianceReport` with per-parameter pass/fail/warning status and recommendations.

### Emergency Standards

Emergency lighting compliance checking (`compliance/emergency_standards.py`) provides threshold requirements for escape routes and open areas, including minimum illuminance along escape paths and battery autonomy requirements.

### EN 13032

Photometric data presentation compliance (`compliance/en13032.py`) checks photometric file quality and reporting conventions.


## Reporting and Export

### PDF Reports

Luxera generates PDF reports using ReportLab:

- EN 12464 compliance reports with metadata, luminaire schedules, per-grid statistics, compliance tables, and embedded plots
- EN 13032 photometric data reports
- Roadway reports with grid layout diagrams and metric tables
- Emergency lighting reports with escape route analysis
- Daylight reports with DF/DA/sDA/UDI summaries

### Client Bundles

The client bundle exporter (`export/client_bundle.py`) packages calculation results, reports, and plots into a ZIP archive for delivery.

### Debug Bundles

The debug bundle exporter (`export/debug_bundle.py`) packages the project snapshot, calculation artifacts, manifest, and checksums for reproducibility auditing.

### Backend Comparison

The backend comparison exporter (`export/backend_comparison.py`) generates side-by-side HTML comparisons between CPU and Radiance backend results for validation.


## Interactive GUI

The GUI (`luxera/gui/`) is built with PySide6 and provides:

- Workspace layout with dockable panels
- Project tree with room/luminaire/grid hierarchy
- Inspector panel for editing selected objects
- Job manager for running calculations
- Results viewer with tabular data and embedded plots
- 3D viewport (OpenGL) with orbit/pan/zoom, room/luminaire/grid rendering, and storey-based streaming
- 2D viewport with plan projection, linework extraction, and drafting output
- Copilot panel for agentic AI interaction (natural language commands, diff preview, approval workflow)
- Assistant panel (extended copilot) with design solve, iteration controls, summary cards, tool log
- Dark and light themes (QSS stylesheets)
- Recent files tracking
- Drag-and-drop IES file loading

Launch:

```bash
python -m luxera.cli gui
```


## Agentic AI Runtime

Luxera includes an agentic AI system (`luxera/agent/`) designed for natural language interaction with the lighting design workflow.

### Tool Registry

The `AgentToolRegistry` (`agent/tools/registry.py`) maintains a permission-tagged registry of callable tools. Each tool has a name, callable, and permission level. The runtime enforces that mutating operations require explicit approval before execution.

Available tool categories:

- `project.*` -- open, save, summarize, grid management
- `geom.*` -- import geometry, clean surfaces, detect rooms
- `project.diff.*` -- propose and apply layout diffs
- `optim.*` -- search, optimize, apply optimized layouts
- `job.*` -- run calculation jobs
- `report.*` -- generate PDF/HTML reports
- `bundle.*` -- export client and debug bundles
- `results.*` -- summarize results, render heatmaps
- `session.*` -- save/load session state

### Runtime Execution

The `AgentRuntime` (`agent/runtime.py`) processes natural language intents and produces structured outputs:

- `AgentPlan` -- ordered list of steps with status
- `AgentProjectDiff` -- preview of proposed changes with per-operation detail
- `RunManifest` -- execution metadata, timing, and result references
- `AgentSessionLog` -- tool call trace and warnings
- `RuntimeAction` -- actions requiring user approval (apply diff, run job)

### Skills

The skills system (`agent/skills/`) provides domain-specific capabilities:

- `setup` -- project initialization workflows
- `layout` -- luminaire placement and arrangement
- `optimize` -- iterative design optimization
- `compliance` -- standards checking and remediation
- `reporting` -- report generation
- `daylight` -- daylight analysis workflows
- `emergency` -- emergency lighting workflows

### Audit Trail

Every agent action is logged to the project's `agent_history` via `append_audit_event()`, recording the action, plan, tool calls, artifacts produced, warnings, and metadata. This provides a complete audit trail of AI-assisted design decisions.

### GUI Integration

The copilot panel (`gui/widgets/copilot_panel.py`) provides:

- Natural language input field
- Plan preview display
- Diff preview with per-operation checkboxes for selective approval
- Select all / select none controls
- Apply, Run, and Apply+Run approval buttons
- Undo/redo for assistant changes
- Audit log display


## Optimization

The optimization module (`luxera/optim/`) provides:

### Deterministic Search

`run_deterministic_search()` evaluates a grid of candidate luminaire layouts against multi-objective criteria:

- Target illuminance (minimize deviation from target)
- Uniformity (maximize U0 = Emin/Eavg)
- UGR (minimize, constrain below threshold)
- Energy/power density (minimize)

Candidates are ranked and the top-N are returned with full result data.

### Optimizer

`run_optimizer()` wraps the search with additional controls:

- Configurable candidate limits
- Constraint specifications (target lux, minimum uniformity, maximum UGR)
- Artifact output (JSON with ranked candidates and per-candidate metrics)
- Integration with the agent runtime for propose-and-apply workflows


## Radiance Backend

Luxera includes a Radiance backend adapter (`luxera/backends/`) for cross-validation and advanced simulation:

- Automatic detection of Radiance tools (oconv, rtrace)
- Scene export to Radiance format (geometry, materials, luminaire proxies)
- rtrace-based illuminance sampling on calculation grids
- Roadway-specific Radiance pipeline
- Manifest generation with tool versions and run parameters
- Backend comparison export for CPU vs. Radiance validation

The Radiance backend requires a separate Radiance installation. It is optional and not required for core functionality.


## Testing

### Test Suite

The test suite contains 230 test files covering:

- Parser correctness (IES, LDT, tilt files, edge cases)
- Photometry model and sampling
- Geometry operations (BVH, CSG, curves, cleaning, topology, triangulation)
- Calculation engines (direct, radiosity, UGR, roadway, daylight, emergency)
- Project schema, validation, migration, diff, history
- CLI workflows (init, add, run, export, compare)
- Import/export pipelines (DXF, IFC, OBJ, mesh)
- Agent runtime, tool registry, session management
- GUI import and widget instantiation
- Reporting and export (PDF, bundles, heatmaps)
- Optimization search and optimizer

### Gate Tests

The `tests/gates/` directory contains release-hardening gate tests:

- `test_gate_determinism.py` -- identical inputs produce identical outputs across runs
- `test_gate_agent_approvals.py` -- mutating operations blocked without approval
- `test_gate_failure_recovery.py` -- missing assets produce errors, not partial artifacts
- `test_gate_dirty_imports.py` -- malformed geometry imports handled gracefully
- `test_gate_edit_propagation.py` -- edits propagate correctly through dependent objects
- `test_gate_plan_views.py` -- plan view projections match expected output
- `test_gate_radiance_delta.py` -- CPU vs Radiance results within tolerance

Plus contract tests for indoor, roadway, emergency, daylight, and report workflows.

### Running Tests

```bash
# Fast tests (excludes slow, radiance, and gui markers)
make test
# or
pytest -q

# All tests including slow integration tests
make test-all
# or
pytest -q -m ""

# Gate tests only
make gates

# Performance benchmark
make perf

# Full release gate check
make release-check

# Release gates including Radiance validation
make release-check-radiance
```

### Golden Regression

The golden regression harness (`tests/golden/`) stores expected calculation artifacts for reference projects. The CLI provides `golden run`, `golden compare`, and `golden update` commands for maintaining regression baselines.


## Examples

### Indoor Office

`examples/indoor_office/` contains a complete indoor office project:

- 6x8m office room with standard reflectances
- IES photometric asset
- Workplane calculation grid at 0.8m
- Direct illuminance job

Run end-to-end:

```bash
python -m luxera.cli run-all examples/indoor_office/office.luxera.json \
    --job office_direct --report --bundle
```

### Roadway

`examples/roadway_basic/` contains a roadway lighting project:

- Road layout with lane definitions
- Roadway luminaire placement
- Roadway calculation grid

Run:

```bash
python -m luxera.cli run-all examples/roadway_basic/road.luxera.json \
    --job road_direct --report
```


## Design Principles

1. **Separation of concerns**: Parse, validate, derive, calculate, present. Each stage is independently testable and the GUI is a thin layer over the core library.

2. **Deterministic by default**: Calculation results are reproducible given the same inputs. Random seeds are explicit and persisted. Job hashes are content-addressed.

3. **Immutable results**: Calculated results are written to content-addressed directories and never mutated. Comparisons reference specific result hashes.

4. **Schema-driven**: The project file is the single source of truth. All state flows through the typed schema. Migrations handle version evolution.

5. **Transactional operations**: Scene modifications go through the ops layer, which supports grouped undo/redo and rebuild replay.

6. **Auditable AI**: Every agent action is logged with its plan, tool calls, diffs, and artifacts. No mutation occurs without explicit approval.

7. **No OS-specific dependencies**: The core library runs on any platform with Python 3.11+. GUI dependencies (PySide6) and external backends (Radiance) are optional.


## Specifications and Contracts

Detailed specifications are maintained in `docs/spec/`:

| Document | Description |
|----------|-------------|
| `AGI32_PARITY.md` | Feature parity tracking against AGi32-class workflows |
| `solver_contracts.md` | Calculation engine input/output contracts |
| `coordinate_conventions.md` | Axis conventions and import transforms |
| `photometry_contracts.md` | Photometric data handling contracts |
| `indoor_workflow.md` | Indoor calculation workflow specification |
| `roadway_workflow.md` | Roadway calculation workflow specification |
| `roadway_grid_definition.md` | Roadway grid layout conventions |
| `daylight_contract.md` | Daylight engine contracts |
| `emergency_contract.md` | Emergency lighting engine contracts |
| `ugr_contract.md` | UGR calculation contracts and assumptions |
| `geometry_pipeline.md` | Geometry import/clean/export pipeline |
| `report_contracts.md` | Report generation contracts |
| `runner_persistence.md` | Job runner result persistence contracts |
| `validation_policy.md` | IES file validation rule policy |
| `limits_and_assumptions.md` | Known limitations and simplifying assumptions |
| `feature_matrix.md` | Feature scope at contract level |

The `docs/agent/` directory contains specifications for the agentic AI system.
