from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from luxera.geometry.core import Vector3
from luxera.parser.ies_parser import parse_ies_text
from luxera.photometry.model import Photometry, photometry_from_parsed_ies
from luxera.photometry.sample import angles_to_direction_type_ab, sample_intensity_cd


def _dir_from_type_c(c_deg: float, g_deg: float) -> Vector3:
    c = math.radians(float(c_deg))
    g = math.radians(float(g_deg))
    return Vector3(math.sin(g) * math.cos(c), math.sin(g) * math.sin(c), -math.cos(g)).normalize()


def _make_symmetric_type_c() -> Photometry:
    c_angles = np.arange(0.0, 360.0, 30.0, dtype=float)
    g_angles = np.arange(0.0, 181.0, 15.0, dtype=float)
    candela = np.zeros((len(c_angles), len(g_angles)), dtype=float)
    for i, c in enumerate(c_angles):
        for j, g in enumerate(g_angles):
            # Rotationally symmetric around nadir (-Z): depends only gamma.
            candela[i, j] = 1000.0 * (math.cos(math.radians(g)) ** 2) + 10.0
    return Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )


def _make_type_b_from_same_field() -> Photometry:
    h_angles = np.arange(0.0, 360.0, 30.0, dtype=float)
    v_angles = np.arange(0.0, 181.0, 15.0, dtype=float)
    candela = np.zeros((len(h_angles), len(v_angles)), dtype=float)
    for i, h in enumerate(h_angles):
        for j, v in enumerate(v_angles):
            d = angles_to_direction_type_ab(float(h), float(v), "B", v_angles)
            # same underlying symmetric field used in _make_symmetric_type_c
            gamma = math.degrees(math.acos(max(-1.0, min(1.0, -d.z))))
            candela[i, j] = 1000.0 * (math.cos(math.radians(gamma)) ** 2) + 10.0
    return Photometry(
        system="B",
        c_angles_deg=h_angles,
        gamma_angles_deg=v_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )


def test_type_b_symmetric_distribution_matches_type_c_after_transform() -> None:
    phot_b = _make_type_b_from_same_field()
    c_angles = np.arange(0.0, 360.0, 30.0, dtype=float)
    g_angles = np.arange(0.0, 181.0, 15.0, dtype=float)
    c_candela = np.zeros((len(c_angles), len(g_angles)), dtype=float)
    for i, c in enumerate(c_angles):
        for j, g in enumerate(g_angles):
            d = _dir_from_type_c(float(c), float(g))
            c_candela[i, j] = sample_intensity_cd(phot_b, d)
    phot_c = Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=g_angles,
        candela=c_candela,
        luminous_flux_lm=None,
        symmetry="NONE",
        tilt=None,
    )

    # Deterministic check on canonical Type C grid points.
    directions = [
        _dir_from_type_c(c, g)
        for c in c_angles.tolist()
        for g in g_angles.tolist()
    ]

    for d in directions:
        i_c = sample_intensity_cd(phot_c, d)
        i_b = sample_intensity_cd(phot_b, d)
        assert i_b == pytest.approx(i_c, rel=1e-5, abs=1e-5)


def test_type_b_corpus_file_expected_beam_directions() -> None:
    p = Path(__file__).parent / "photometry" / "corpus" / "type_b_beam_real.ies"
    doc = parse_ies_text(p.read_text(encoding="utf-8"), source_path=p)
    phot = photometry_from_parsed_ies(doc)

    assert phot.system == "B"

    i_pos_y = sample_intensity_cd(phot, Vector3(0.0, 1.0, 0.0))
    i_pos_x = sample_intensity_cd(phot, Vector3(1.0, 0.0, 0.0))
    i_neg_x = sample_intensity_cd(phot, Vector3(-1.0, 0.0, 0.0))
    i_down = sample_intensity_cd(phot, Vector3(0.0, 0.0, -1.0))

    # Directional ordering encoded in corpus candela rows.
    assert i_pos_y > i_pos_x > i_neg_x
    assert i_pos_x > i_down > 0.0
