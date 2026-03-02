from __future__ import annotations

from luxera.project.scenes import ControlGroup, LightScene, SceneManager
from luxera.project.schema import LuminaireInstance, Project, RotationSpec, TransformSpec


def _project_with_luminaires() -> Project:
    p = Project(name="Scenes")
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.extend(
        [
            LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec((1.0, 1.0, 3.0), rot), flux_multiplier=1.0),
            LuminaireInstance(id="l2", name="L2", photometry_asset_id="a1", transform=TransformSpec((2.0, 1.0, 3.0), rot), flux_multiplier=1.0),
            LuminaireInstance(id="l3", name="L3", photometry_asset_id="a1", transform=TransformSpec((3.0, 1.0, 3.0), rot), flux_multiplier=1.0),
        ]
    )
    return p


def test_create_group_and_scene():
    p = _project_with_luminaires()
    m = SceneManager(p)
    m.add_group(ControlGroup(id="g1", name="Front", luminaire_ids=["l1", "l2"], default_dimming=1.0))
    m.add_group(ControlGroup(id="g2", name="Rear", luminaire_ids=["l3"], default_dimming=1.0))
    m.add_scene(
        LightScene(id="s1", name="Meeting", description="Meeting mode", dimming_overrides={"g1": 0.6, "g2": 0.8})
    )
    assert len(p.control_groups) == 2
    assert len(p.light_scenes) == 1


def test_effective_dimming():
    p = _project_with_luminaires()
    m = SceneManager(p)
    m.add_group(ControlGroup(id="a", name="A", luminaire_ids=["l1", "l2"], default_dimming=1.0))
    m.add_group(ControlGroup(id="b", name="B", luminaire_ids=["l3"], default_dimming=1.0))
    m.add_scene(LightScene(id="scene", name="Presentation", description="", dimming_overrides={"a": 0.5, "b": 0.8}))
    d = m.get_effective_dimming("scene")
    assert d["l1"] == 0.5
    assert d["l2"] == 0.5
    assert d["l3"] == 0.8


def test_apply_scene_modifies_flux():
    p = _project_with_luminaires()
    m = SceneManager(p)
    m.add_group(ControlGroup(id="a", name="A", luminaire_ids=["l1", "l2"], default_dimming=1.0))
    m.add_scene(LightScene(id="scene", name="Presentation", description="", dimming_overrides={"a": 0.5}))
    out = m.apply_scene_to_project("scene")
    by_id = {l.id: l for l in out.luminaires}
    assert by_id["l1"].flux_multiplier == 0.5
    assert by_id["l2"].flux_multiplier == 0.5


def test_unassigned_luminaires_full():
    p = _project_with_luminaires()
    m = SceneManager(p)
    m.add_group(ControlGroup(id="a", name="A", luminaire_ids=["l1"], default_dimming=0.7))
    m.add_scene(LightScene(id="scene", name="Only A", description="", dimming_overrides={}))
    d = m.get_effective_dimming("scene")
    assert d["l1"] == 0.7
    assert d["l2"] == 1.0
    assert d["l3"] == 1.0


def test_invalid_luminaire_id_raises():
    p = _project_with_luminaires()
    m = SceneManager(p)
    try:
        m.add_group(ControlGroup(id="bad", name="Bad", luminaire_ids=["missing"], default_dimming=1.0))
    except ValueError:
        return
    assert False, "expected ValueError for missing luminaire id"


def test_run_all_scenes():
    p = _project_with_luminaires()
    m = SceneManager(p)
    m.add_group(ControlGroup(id="a", name="A", luminaire_ids=["l1"], default_dimming=0.5))
    m.add_scene(LightScene(id="s1", name="S1", description="", dimming_overrides={}))
    m.add_scene(LightScene(id="s2", name="S2", description="", dimming_overrides={"a": 0.2}))
    calls: list[Project] = []

    def _runner(proj: Project):
        calls.append(proj)
        return {"ok": True, "n": len(proj.luminaires)}

    out = m.run_all_scenes(_runner, p)
    assert set(out.keys()) == {"s1", "s2"}
    assert len(calls) == 2

