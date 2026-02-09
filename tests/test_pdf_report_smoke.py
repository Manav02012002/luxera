from pathlib import Path

import pytest

from luxera.parser.pipeline import parse_and_analyse_ies
from luxera.plotting.plots import save_default_plots
from luxera.export.pdf_report import build_pdf_report

pytestmark = pytest.mark.slow


def test_pdf_report_smoke(tmp_path: Path):
    text = """IESNA:LM-63-2002
[MANUFAC] Demo
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""
    res = parse_and_analyse_ies(text)
    assert res.doc.angles is not None and res.doc.candela is not None

    plots = save_default_plots(res.doc, tmp_path, stem="smoke")
    pdf_path = tmp_path / "smoke_report.pdf"
    out = build_pdf_report(res, plots, pdf_path, source_file=None)

    assert out.pdf_path.exists()
    assert out.pdf_path.stat().st_size > 0
