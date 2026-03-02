from __future__ import annotations

from pathlib import Path

from luxera.agent.conversation import ConversationEngine, ConversationTurn
from luxera.project.io import save_project_schema
from luxera.project.schema import LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _make_project(tmp_path: Path) -> Path:
    p = Project(name="ConvProject", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="Room", width=6.0, length=8.0, height=3.0))
    ies = tmp_path / "fixture.ies"
    ies.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 1.0, 2.8), rotation=rot),
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="L2",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(4.0, 5.0, 2.8), rotation=rot),
        )
    )
    proj = tmp_path / "project.json"
    save_project_schema(p, proj)
    return proj


def test_constraint_extraction_illuminance(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    eng._extract_constraints("I need 500 lux in the room")
    assert eng.constraints.target_illuminance == 500.0


def test_constraint_extraction_ugr(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    eng._extract_constraints("UGR must be below 19")
    assert eng.constraints.target_ugr == 19.0


def test_constraint_extraction_standard(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    eng._extract_constraints("EN 12464 office")
    assert eng.constraints.standard == "EN 12464-1"
    assert eng.constraints.activity_type is not None
    assert "OFFICE" in eng.constraints.activity_type


def test_history_trimming(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    for i in range(30):
        eng.history.append(
            ConversationTurn(
                role="user" if i % 2 == 0 else "assistant",
                content=f"turn {i}",
                tool_calls=[],
                results_summary=None,
                timestamp="2026-03-02T00:00:00Z",
            )
        )
    trimmed = eng._trim_history()
    assert len(trimmed) == 21


def test_project_summary(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    summary = eng._build_project_summary()
    assert "Rooms: 1" in summary
    assert "Luminaires: 2" in summary


def test_session_save_load_roundtrip(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    eng.process_message("I need 500 lux")
    session = tmp_path / "session.json"
    eng.save_session(session)

    eng2 = ConversationEngine(str(proj), llm_client=None)
    eng2.load_session(session)

    assert eng2.constraints.target_illuminance == 500.0
    assert len(eng2.history) == len(eng.history)
    assert eng2.history[0].content == eng.history[0].content


def test_fallback_without_llm(tmp_path: Path) -> None:
    proj = _make_project(tmp_path)
    eng = ConversationEngine(str(proj), llm_client=None)
    out = eng.process_message("summarize project")
    assert isinstance(out, str)
    assert out
