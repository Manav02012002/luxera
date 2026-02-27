from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping


HandlerMap = Mapping[str, Callable[[argparse.Namespace], int]]


def register_tool_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser], handlers: HandlerMap) -> None:
    golden = sub.add_parser("golden", help="Golden regression harness tooling.")
    golden_sub = golden.add_subparsers(dest="golden_cmd", required=True)

    golden_run = golden_sub.add_parser("run", help="Run one golden case (or all) and emit produced artifacts.")
    golden_run.add_argument("case_id", help="Golden case id or 'all'")
    golden_run.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    golden_run.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    golden_run.set_defaults(func=handlers["golden_run"])

    golden_compare = golden_sub.add_parser("compare", help="Run and compare one golden case (or all) against expected.")
    golden_compare.add_argument("case_id", help="Golden case id or 'all'")
    golden_compare.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    golden_compare.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    golden_compare.set_defaults(func=handlers["golden_compare"])

    golden_update = golden_sub.add_parser("update", help="Run and overwrite expected artifacts for one case (or all).")
    golden_update.add_argument("case_id", help="Golden case id or 'all'")
    golden_update.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    golden_update.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    golden_update.add_argument("--yes", action="store_true", help="Required acknowledgement for overwriting expected outputs")
    golden_update.set_defaults(func=handlers["golden_update"])

    photometry = sub.add_parser("photometry", help="Photometry tooling.")
    photometry_sub = photometry.add_subparsers(dest="phot_cmd", required=True)

    verify = photometry_sub.add_parser("verify", help="Verify photometry file conventions/sanity/hash.")
    verify.add_argument("file", help="Path to IES/LDT file")
    verify.add_argument("--format", default=None, help="Override format (IES or LDT)")
    verify.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    verify.set_defaults(func=handlers["photometry_verify"])

    library = sub.add_parser("library", help="Local photometry library manager.")
    library_sub = library.add_subparsers(dest="library_cmd", required=True)

    index = library_sub.add_parser("index", help="Index IES/LDT files from a folder into a local DB.")
    index.add_argument("folder", help="Folder to scan recursively for IES/LDT files")
    index.add_argument("--out", required=True, help="Output SQLite DB path")
    index.set_defaults(func=handlers["library_index"])

    search = library_sub.add_parser("search", help='Search indexed photometry DB with query string filters.')
    search.add_argument("--db", required=True, help="Path to library SQLite DB")
    search.add_argument("--query", required=True, help='Query, e.g. \'manufacturer:acme lumens>=2000 cct=4000 beam<80\'')
    search.add_argument("--limit", type=int, default=100, help="Maximum rows to return")
    search.add_argument("--json", action="store_true", help="Print JSON payload")
    search.set_defaults(func=handlers["library_search"])

    geometry = sub.add_parser("geometry", help="Geometry import/clean tooling.")
    geometry_sub = geometry.add_subparsers(dest="geom_cmd", required=True)

    geometry_import = geometry_sub.add_parser("import", help="Import geometry into a project (DXF/OBJ/GLTF/FBX/SKP/IFC/DWG).")
    geometry_import.add_argument("project", help="Path to project JSON")
    geometry_import.add_argument("file", help="Path to geometry file")
    geometry_import.add_argument("--format", default=None, help="Override format: DXF|OBJ|GLTF|FBX|SKP|IFC|DWG")
    geometry_import.add_argument("--dxf-scale", type=float, default=1.0, help="DXF units -> meters scale")
    geometry_import.add_argument("--length-unit", default=None, help="Optional unit override: m|mm|cm|ft|in")
    geometry_import.add_argument("--scale-to-meters", type=float, default=None, help="Optional explicit unit scale")
    geometry_import.add_argument("--ifc-window-vt", type=float, default=0.70, help="IFC default visible transmittance for imported windows")
    geometry_import.add_argument("--ifc-room-width", type=float, default=5.0, help="IFC fallback room width")
    geometry_import.add_argument("--ifc-room-length", type=float, default=5.0, help="IFC fallback room length")
    geometry_import.add_argument("--ifc-room-height", type=float, default=3.0, help="IFC fallback room height")
    geometry_import.add_argument("--ifc-source-up-axis", default="Z_UP", choices=["Z_UP", "Y_UP"], help="IFC source up-axis convention")
    geometry_import.add_argument(
        "--ifc-source-handedness",
        default="RIGHT_HANDED",
        choices=["RIGHT_HANDED", "LEFT_HANDED"],
        help="IFC source handedness convention",
    )
    geometry_import.add_argument(
        "--layer-map",
        action="append",
        default=[],
        help="Layer role override for DXF (repeatable): LAYER=wall|door|window|room|grid|unmapped",
    )
    geometry_import.set_defaults(func=handlers["geometry_import"])

    geometry_clean = geometry_sub.add_parser("clean", help="Clean project surfaces (normals, gaps, coplanar merge).")
    geometry_clean.add_argument("project", help="Path to project JSON")
    geometry_clean.add_argument("--snap-tolerance", type=float, default=1e-3, help="Vertex snap tolerance in meters")
    geometry_clean.add_argument("--no-merge", action="store_true", help="Disable coplanar merge")
    geometry_clean.add_argument("--detect-rooms", action="store_true", help="Detect room volumes from cleaned surfaces")
    geometry_clean.set_defaults(func=handlers["geometry_clean"])

    parity = sub.add_parser("parity", help="Parity harness for reference scene packs.")
    parity_sub = parity.add_subparsers(dest="parity_cmd", required=True)

    parity_run = parity_sub.add_parser("run", help="Run parity corpus selection and emit run artifacts.")
    parity_run.add_argument("--selector", default=None, help="Selector YAML path (e.g., parity/ci/fast_selection.yaml)")
    parity_run.add_argument("--pack", default=None, help="Single pack id to run (e.g., indoor_basic)")
    parity_run.add_argument("--baseline", default="luxera", help="Baseline id (default: luxera)")
    parity_run.add_argument("--out", default=None, help="Output directory (default: out/parity_runs/<timestamp>)")
    parity_run.add_argument("--parity-root", default="parity", help="Parity corpus root (default: parity/)")
    parity_run.set_defaults(func=handlers["parity_run"])

    parity_update = parity_sub.add_parser("update", help="Run parity corpus and update expected goldens (luxera baseline only).")
    parity_update.add_argument("--selector", default=None, help="Selector YAML path (e.g., parity/ci/fast_selection.yaml)")
    parity_update.add_argument("--pack", default=None, help="Single pack id to update (e.g., indoor_basic)")
    parity_update.add_argument("--baseline", default="luxera", help="Baseline id; must be luxera")
    parity_update.add_argument("--out", default=None, help="Output directory (default: out/parity_runs/<timestamp>)")
    parity_update.add_argument("--parity-root", default="parity", help="Parity corpus root (default: parity/)")
    parity_update.add_argument("--force", action="store_true", default=False, help="Allow update even if git working tree is dirty")
    parity_update.set_defaults(func=handlers["parity_update"], update_goldens=True)

    parity_report = parity_sub.add_parser("report", help="Print summary details from a parity corpus run directory.")
    parity_report.add_argument("--in", dest="in_dir", required=True, help="Parity run directory containing summary.json and summary.md")
    parity_report.set_defaults(func=handlers["parity_report"])

    parity_test = parity_sub.add_parser("test", help="Run and compare legacy parity pack against expected tolerances.")
    parity_test.add_argument("pack_dir", help="Path to pack directory (expects expected/expected.json)")
    parity_test.set_defaults(func=handlers["parity_test"])

    validate = sub.add_parser("validate", help="Validation harness for case suites in tests/validation.")
    validate_sub = validate.add_subparsers(dest="validate_cmd", required=True)

    validate_list = validate_sub.add_parser("list", help="List discovered validation suites/cases.")
    validate_list.add_argument("--root", default=None, help="Validation root (default: tests/validation)")
    validate_list.set_defaults(func=handlers["validate_list"])

    validate_run = validate_sub.add_parser("run", help="Run validation suite or case target.")
    validate_run.add_argument("target", help="Suite or suite/case_id")
    validate_run.add_argument("--out", required=True, help="Output directory for run artifacts")
    validate_run.add_argument("--root", default=None, help="Validation root (default: tests/validation)")
    validate_run.set_defaults(func=handlers["validate_run"])

    validate_report = validate_sub.add_parser("report", help="Run suite and emit markdown/json summary.")
    validate_report.add_argument("suite", help="Suite or suite/case_id")
    validate_report.add_argument("--out", required=True, help="Output directory for report artifacts")
    validate_report.add_argument("--root", default=None, help="Validation root (default: tests/validation)")
    validate_report.set_defaults(func=handlers["validate_report"])

    agent = sub.add_parser("agent", help='Agent batch/context. Example: luxera agent "<instruction>" --project p.json --approve-all --out out/')
    agent.add_argument("instruction", nargs="?", default=None, help="Instruction for headless agent batch mode")
    agent.add_argument("agent_mode", nargs="?", default=None, help='Optional mode: "context"')
    agent.add_argument("context_action", nargs="?", default=None, help='Context action when mode=context: "show"|"reset"')
    agent.add_argument("--project", required=False, default=None, help="Path to project JSON")
    agent.add_argument("--approve-all", action="store_true", default=False, help="Approve all gated actions (diff apply + run job)")
    agent.add_argument("--out", default="out", help="Output directory for batch artifacts")
    agent.set_defaults(func=handlers["agent"])
