from __future__ import annotations

import json
from pathlib import Path

from luxera.cli import main


def _ies_text() -> str:
    return """IESNA:LM-63-2002
[MANUFAC] CLI Manufacturer
[LUMINAIRE] CLI Fixture
[LUMCAT] CLI-100
[CCT] 4000
[BEAM] 60
TILT=NONE
1 2000 1 3 2 1 2 0.50 0.50 0.10
0 30 90
0 180
100 80 20
100 80 20
"""


def test_cli_library_index_and_search(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "lib"
    folder.mkdir()
    (folder / "fixture.ies").write_text(_ies_text(), encoding="utf-8")
    db = tmp_path / "library.db"

    rc = main(["library", "index", str(folder), "--out", str(db)])
    assert rc == 0
    assert db.exists()
    _ = capsys.readouterr()

    rc = main(["library", "search", "--db", str(db), "--query", "manufacturer:cli", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert len(payload) == 1
    assert payload[0]["catalog_number"] == "CLI-100"
