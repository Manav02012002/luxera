from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from luxera.cache.photometry_cache import load_lut_from_cache, save_lut_to_cache
from luxera.geometry.core import Vector3
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, RoomSpec, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec, CalcGrid, JobSpec
from luxera.runner import run_job
from luxera.photometry.interp import build_interpolation_lut, sample_lut_intensity_cd
from luxera.photometry.ies import parse_ies_canonical
from luxera.photometry.ldt import parse_ldt_canonical
from luxera.photometry.sample import sample_intensity_cd
from luxera.photometry.canonical import canonical_from_photometry
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.model import photometry_from_parsed_ldt
from luxera.photometry.model import Photometry


def test_ies_canonical_hash_is_deterministic() -> None:
    p = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    c1 = parse_ies_canonical(text, source_path=p)
    c2 = parse_ies_canonical(text, source_path=p)
    assert c1.content_hash == c2.content_hash


def test_interpolation_lut_cache_roundtrip(tmp_path: Path) -> None:
    p = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    can = parse_ies_canonical(text, source_path=p)
    lut = build_interpolation_lut(can)
    out = save_lut_to_cache(tmp_path / "photometry", lut)
    assert out.exists()
    loaded = load_lut_from_cache(tmp_path / "photometry", can.content_hash)
    assert loaded is not None
    assert loaded.content_hash == lut.content_hash
    assert loaded.intensity_cd.shape == lut.intensity_cd.shape


def test_interpolation_lut_sampling_matches_runtime_sampling() -> None:
    p = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    parsed = parse_ies_text(text, source_path=p)
    phot = photometry_from_parsed_ies(parsed)
    can = parse_ies_canonical(text, source_path=p)
    lut = build_interpolation_lut(can)
    d = Vector3(0.25, 0.4, -0.88).normalize()
    direct = sample_intensity_cd(phot, d)
    via_lut = sample_lut_intensity_cd(lut, d)
    assert via_lut == pytest.approx(direct, rel=1e-6, abs=1e-9)


def test_runtime_emits_photometry_lut_cache(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="cache_emit", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3, room_id="r1"))
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", settings={"use_occlusion": False}, seed=0))
    proj = tmp_path / "p.json"
    save_project_schema(p, proj)

    _ = run_job(proj, "j1")
    cache_dir = tmp_path / ".luxera" / "cache" / "photometry"
    assert cache_dir.exists()
    npz_files = list(cache_dir.glob("*.npz"))
    assert npz_files


def test_ies_canonical_smoke_corpus_repo_files() -> None:
    roots = [
        Path("tests/fixtures/photometry"),
        Path("tests/fixtures/ies"),
        Path("tests/golden/projects"),
        Path("tests/validation/scenes"),
    ]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.ies"):
            if "lm63_edgecases" in str(p) and p.name.startswith("fail_"):
                continue
            paths.append(p.resolve())

    unique_paths = sorted(set(paths))
    assert len(unique_paths) >= 10
    for p in unique_paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        c = parse_ies_canonical(text, source_path=p)
        assert c.system in {"A", "B", "C"}
        assert c.intensity_cd.shape == (c.angles_h_deg.size, c.angles_v_deg.size)
        assert len(c.content_hash) == 64


def test_ldt_canonical_hash_and_lut_sampling() -> None:
    p = Path("tests/fixtures/photometry/synthetic_basic.ldt").resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    c1 = parse_ldt_canonical(text)
    c2 = parse_ldt_canonical(text)
    assert c1.content_hash == c2.content_hash
    assert c1.source_format == "LDT"

    parsed = parse_ldt_text(text)
    phot = photometry_from_parsed_ldt(parsed)
    lut = build_interpolation_lut(c1)

    d = Vector3(0.75, 0.1, -0.65).normalize()
    direct = sample_intensity_cd(phot, d)
    via_lut = sample_lut_intensity_cd(lut, d)
    assert via_lut == pytest.approx(direct, rel=1e-6, abs=1e-9)


def test_lut_sampling_matches_runtime_at_type_c_seam_and_symmetry() -> None:
    c = np.array([0.0, 90.0, 180.0, 270.0], dtype=float)
    g = np.array([90.0], dtype=float)
    # Asymmetric values to expose seam interpolation and symmetry handling.
    candela = np.array([[1000.0], [200.0], [100.0], [0.0]], dtype=float)
    phot = Photometry(
        system="C",
        c_angles_deg=c,
        gamma_angles_deg=g,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="BILATERAL",
        tilt=None,
    )
    can = canonical_from_photometry(phot, source_format="IES")
    lut = build_interpolation_lut(can)

    # C=315 maps to C=45 under bilateral symmetry.
    d = Vector3(np.sqrt(0.5), -np.sqrt(0.5), 0.0).normalize()
    direct = sample_intensity_cd(phot, d)
    via_lut = sample_lut_intensity_cd(lut, d)
    assert via_lut == pytest.approx(direct, rel=1e-6, abs=1e-9)
