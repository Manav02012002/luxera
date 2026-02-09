Luxera

Luxera is a cross-platform, open-source lighting analysis and visualisation tool focused on IES (LM-63) photometric data.
It provides a clean, OS-agnostic alternative to legacy lighting software, with a modern Python core, validation engine, plotting, PDF reporting, and an interactive GUI.

Status: Active development (v0.1.0)
Platforms: macOS, Linux, Windows
License: TBD (recommended: MIT or Apache-2.0)

Motivation

Professional lighting tools such as DIALux and AGi32 are:

Windows-only

Closed-source

Difficult to integrate into modern computational workflows

Not easily scriptable or extensible

Luxera aims to:

Be OS-agnostic

Provide a transparent, testable core

Support both CLI automation and interactive GUI workflows

Serve as a foundation for future lighting simulation and design tooling

Features (Current)
1. IES (LM-63) Parsing

Luxera implements a robust parser for IES photometric files, supporting:

Standard headers (e.g. IESNA:LM-63-2002)

Keyword blocks ([MANUFAC], [LUMCAT], etc.)

Photometric geometry

Vertical and horizontal angle grids

Candela distributions

Parsing is strict but informative, with line-aware error reporting.

2. Validation Engine

Luxera includes a modular validation framework that:

Applies rule-based checks to parsed IES data

Classifies findings as ERROR, WARNING, or INFO

Produces both a structured report and human-readable summaries

The validation system is designed to be:

Extensible (rules live in luxera/validation/rules)

Deterministic and testable

Suitable for both automated pipelines and GUI display

3. Derived Photometric Metrics

From raw IES data, Luxera computes:

Peak candela value

Peak location (horizontal & vertical angles)

Candela statistics (min, max, mean, 95th percentile)

Symmetry heuristics (basic inference)

These metrics are used consistently across:

CLI output

GUI tables

PDF reports

4. Plotting & Visualisation

Luxera generates publication-quality plots using Matplotlib:

Intensity curves (candela vs vertical angle)

Polar plots for selected horizontal planes

Plots are saved as PNG files and reused by:

CLI workflows

GUI previews

PDF export

5. PDF Report Export

Luxera can generate a shareable engineering PDF report, including:

Metadata summary

Photometry and geometry details

Derived metrics

Validation findings

Embedded plots (intensity + polar)

This makes Luxera suitable for:

Design documentation

Review workflows

Client or internal reporting

6. Command Line Interface (CLI)

Luxera provides a clean CLI for automation and scripting.

Generate a demo IES file
python -m luxera.cli demo --out data/ies_samples/demo.ies

Analyse and plot an IES file
python -m luxera.cli view path/to/file.ies --out out --stem myfile

Generate plots + PDF
python -m luxera.cli view path/to/file.ies --out out --stem myfile --pdf

7. Interactive GUI (Luxera View)

Luxera includes a cross-platform desktop GUI built with Qt (PySide6).

GUI Features:

Open IES files via dialog or drag & drop

Live display of:

Metadata

Derived metrics

Validation findings

Embedded plot previews

One-click PDF export

Launch the GUI:

python -m luxera.cli gui

Architecture Overview
luxera/
├── parser/        # IES parsing and data structures
├── validation/    # Rule-based validation engine
├── models/        # Core and derived data models
├── derived/       # Computed photometric metrics
├── plotting/      # Matplotlib visualisation
├── export/        # PDF reporting
├── gui/           # Qt-based interactive GUI
├── cli.py         # Unified command-line interface
└── tests/         # Pytest-based test suite


Design principles:

Separation of concerns (parse → validate → derive → present)

Fully testable core logic

GUI as a thin layer on top of the same engine

No OS-specific dependencies

Testing & Reliability

Comprehensive pytest suite

Parser, validation, plotting, PDF, CLI, and GUI imports are all tested

Current test status: ✅ all tests passing

Run tests:

pytest -q

Fast default test set excludes optional markers:

pytest -m "not slow and not radiance and not gui"

Run full suite:

pytest -m ""

Repository cleanup:

python scripts/clean.py

Release zip (artifact excludes caches/build junk):

python scripts/build_release.py --out dist/luxera-release.zip

Installation (Development)
conda create -n luxera python=3.11
conda activate luxera

pip install -e .
pip install reportlab pyside6

Roadmap (Planned)

Short-term:

Recent files list in GUI

Horizontal plane selector for plots

Improved PDF styling (headers, footers, branding)

Medium-term:

Candela heatmaps (H × V)

Project/session files

Export bundles (PDF + images)

Long-term:

Full room / scene modelling

Point-by-point illuminance calculations

DIALux-style workflows on top of Luxera core

Why Luxera Matters

Luxera demonstrates that:

Lighting analysis tools do not need to be OS-locked

Engineering software can be transparent, testable, and modern

A clean computational core enables both automation and GUI use

This project is intended as both:

A practical tool

A foundation for future research-grade and professional lighting software
