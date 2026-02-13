from __future__ import annotations

from pathlib import Path

from luxera.agent.skills.compliance import build_compliance_skill
from luxera.project.io import save_project_schema
from luxera.project.schema import (
    JobResultRef,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    TransformSpec,
)


def _seed_project_with_failed_compliance(tmp_path: Path) -> Path:
    ies_path = tmp_path / "compliance.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    p = Project(name="ComplianceSkill", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 1.0, 2.8), rotation=rot),
            flux_multiplier=1.0,
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="L2",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(4.0, 2.0, 2.8), rotation=rot),
            flux_multiplier=1.0,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", settings={}))
    p.results.append(
        JobResultRef(
            job_id="j1",
            job_hash="hash1",
            result_dir=str(tmp_path / "results" / "j1"),
            summary={
                "compliance_profile": {
                    "status": "FAIL",
                    "avg_ok": False,
                    "uniformity_ok": False,
                    "ugr_ok": True,
                }
            },
        )
    )
    path = tmp_path / "project.json"
    save_project_schema(p, path)
    return path


def test_compliance_skill_proposes_fix_diff(tmp_path: Path) -> None:
    project_path = _seed_project_with_failed_compliance(tmp_path)
    out = build_compliance_skill(str(project_path), domain="indoor", ensure_run=False)
    assert out.run_manifest.get("skill") == "compliance"
    proposals = out.run_manifest.get("proposals", [])
    assert isinstance(proposals, list)
    assert proposals
    assert out.diff.ops
    assert any(op.kind == "luminaire" for op in out.diff.ops)


def test_compliance_skill_can_propose_variant(tmp_path: Path) -> None:
    project_path = _seed_project_with_failed_compliance(tmp_path)
    out = build_compliance_skill(str(project_path), domain="indoor", ensure_run=False, create_variant=True)
    assert out.run_manifest.get("create_variant") is True
    assert out.run_manifest.get("variant_proposal") is not None
    assert len(out.diff.ops) == 1
    op = out.diff.ops[0]
    assert op.kind == "variant"
    assert op.op == "add"
