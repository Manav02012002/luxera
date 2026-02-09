import json
from pathlib import Path

from luxera.cli import main
from luxera.photometry.verify import verify_photometry_file


def test_verify_photometry_file_ies(tmp_path: Path):
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 2 1 2 0.5 0.5 0.2
0 45 90
0 90
100 80 60
90 70 50
""",
        encoding="utf-8",
    )
    result = verify_photometry_file(str(ies_path))
    data = result.to_dict()

    assert data["format"] == "IES"
    assert data["photometric_system"] == "C"
    assert data["counts"]["num_c"] == 2
    assert data["counts"]["num_gamma"] == 3
    assert "coordinate_convention" in data


def test_cli_photometry_verify_json(tmp_path: Path, capsys):
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    rc = main(["photometry", "verify", str(ies_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["format"] == "IES"
    assert payload["counts"]["num_gamma"] == 3
