from __future__ import annotations

import argparse
from pathlib import Path

from luxera.parser.pipeline import parse_and_analyse_ies
from luxera.plotting.plots import save_default_plots
from luxera.export.pdf_report import build_pdf_report


_DEMO_IES_TEXT = """IESNA:LM-63-2002
[MANUFAC] Luxera Demo
[LUMCAT] DEMO-001
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""


def _cmd_demo(args: argparse.Namespace) -> int:
    outpath = Path(args.out).expanduser().resolve()
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(_DEMO_IES_TEXT, encoding="utf-8")
    print(f"Saved demo IES to: {outpath}")
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    ies_path = Path(args.file).expanduser().resolve()
    outdir = Path(args.out).expanduser().resolve()
    stem = args.stem
    make_pdf = bool(args.pdf)

    if not ies_path.exists():
        print(f"[ERROR] File not found: {ies_path}")
        print("        Provide a valid path to a .ies file.")
        return 2
    if not ies_path.is_file():
        print(f"[ERROR] Not a file: {ies_path}")
        return 2

    text = ies_path.read_text(encoding="utf-8", errors="replace")
    res = parse_and_analyse_ies(text)

    if res.doc.photometry is None or res.doc.angles is None or res.doc.candela is None:
        print("[ERROR] Failed to parse photometry/angles/candela; cannot plot/report.")
        return 3

    paths = save_default_plots(res.doc, outdir, stem=stem)

    pdf_path = None
    if make_pdf:
        pdf_path = outdir / f"{stem}_report.pdf"
        build_pdf_report(res, paths, pdf_path, source_file=ies_path)

    print("Luxera View")
    print(f"  File: {ies_path}")
    print(f"  Saved: {paths.intensity_png}")
    print(f"  Saved: {paths.polar_png}")
    if pdf_path is not None:
        print(f"  Saved: {pdf_path}")

    if res.derived is not None:
        print(
            f"  Peak candela: {res.derived.peak_candela:g} "
            f"at (H,V)=({res.derived.peak_location[0]:g}°, {res.derived.peak_location[1]:g}°)"
        )

    if res.report is not None:
        s = res.report.summary
        print(f"  Findings: {s['errors']} error(s), {s['warnings']} warning(s), {s['info']} info")

    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    # Import here so CLI still works even if PySide6 isn't installed
    from luxera.gui.app import run
    return int(run())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="luxera")
    sub = p.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Write a small demo .ies file to disk.")
    demo.add_argument("--out", default="data/ies_samples/demo.ies", help="Output .ies path")
    demo.set_defaults(func=_cmd_demo)

    v = sub.add_parser("view", help="Parse an IES file and save default plots (PNG), optionally PDF.")
    v.add_argument("file", help="Path to .ies file")
    v.add_argument("--out", default="out", help="Output directory (default: out)")
    v.add_argument("--stem", default="luxera_view", help="Filename stem for outputs")
    v.add_argument("--pdf", action="store_true", help="Also generate a PDF report")
    v.set_defaults(func=_cmd_view)

    g = sub.add_parser("gui", help="Launch Luxera View interactive GUI.")
    g.set_defaults(func=_cmd_gui)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
