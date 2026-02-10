from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema


def _write_ies(path: Path) -> None:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )


def test_cli_indoor_workflow_anchor(tmp_path: Path):
    project = tmp_path / "indoor.json"
    ies = tmp_path / "lum.ies"
    _write_ies(ies)

    assert main(["init", str(project), "--name", "IndoorFlow"]) == 0
    assert main(["add-photometry", str(project), str(ies), "--id", "a1"]) == 0
    assert (
        main(
            [
                "add-room",
                str(project),
                "--id",
                "r1",
                "--name",
                "Office",
                "--width",
                "6",
                "--length",
                "8",
                "--height",
                "3",
                "--activity-type",
                "OFFICE_GENERAL",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "add-luminaire",
                str(project),
                "--id",
                "l1",
                "--asset",
                "a1",
                "--x",
                "2.0",
                "--y",
                "2.0",
                "--z",
                "2.8",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "add-grid",
                str(project),
                "--id",
                "g1",
                "--width",
                "6",
                "--height",
                "8",
                "--elevation",
                "0.8",
                "--nx",
                "5",
                "--ny",
                "7",
                "--room-id",
                "r1",
            ]
        )
        == 0
    )
    assert main(["add-profile-presets", str(project)]) == 0
    assert (
        main(
            [
                "add-job",
                str(project),
                "--id",
                "j1",
                "--type",
                "direct",
                "--compliance-profile-id",
                "office_en12464",
            ]
        )
        == 0
    )
    assert main(["run", str(project), "j1"]) == 0

    p = load_project_schema(project)
    assert any(r.job_id == "j1" for r in p.results)

    client_zip = tmp_path / "client.zip"
    debug_zip = tmp_path / "debug.zip"
    assert main(["export-client", str(project), "j1", "--out", str(client_zip)]) == 0
    assert main(["export-debug", str(project), "j1", "--out", str(debug_zip)]) == 0
    assert client_zip.exists()
    assert debug_zip.exists()
