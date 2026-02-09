from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from luxera.core.hashing import sha256_file
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt


@dataclass(frozen=True)
class PhotometryVerifyResult:
    file: str
    file_hash_sha256: str
    format: str
    photometric_system: str
    symmetry: str
    coordinate_convention: str
    angle_ranges_deg: Dict[str, float]
    counts: Dict[str, int]
    candela_stats: Dict[str, float]
    luminous: Dict[str, Optional[float]]
    sanity: Dict[str, bool]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_result(
    path: Path,
    fmt: str,
    system: str,
    symmetry: str,
    c_angles: np.ndarray,
    g_angles: np.ndarray,
    candela: np.ndarray,
    luminous_flux_lm: Optional[float],
    luminous_width_m: Optional[float],
    luminous_length_m: Optional[float],
) -> PhotometryVerifyResult:
    warnings: List[str] = []
    if system in ("A", "B"):
        warnings.append("Photometric system A/B is supported with explicit limits; verify conventions before compliance use.")
    if candela.size and float(np.max(candela)) == 0.0:
        warnings.append("All candela values are zero.")
    if candela.size and float(np.min(candela)) < 0.0:
        warnings.append("Candela values include negatives.")

    return PhotometryVerifyResult(
        file=str(path),
        file_hash_sha256=sha256_file(str(path)),
        format=fmt,
        photometric_system=system,
        symmetry=symmetry,
        coordinate_convention="Local luminaire frame: +Z up, nadir is -Z; C=0 toward +X, C=90 toward +Y",
        angle_ranges_deg={
            "c_min": float(np.min(c_angles)) if c_angles.size else 0.0,
            "c_max": float(np.max(c_angles)) if c_angles.size else 0.0,
            "gamma_min": float(np.min(g_angles)) if g_angles.size else 0.0,
            "gamma_max": float(np.max(g_angles)) if g_angles.size else 0.0,
        },
        counts={"num_c": int(c_angles.size), "num_gamma": int(g_angles.size)},
        candela_stats={
            "min_cd": float(np.min(candela)) if candela.size else 0.0,
            "max_cd": float(np.max(candela)) if candela.size else 0.0,
            "mean_cd": float(np.mean(candela)) if candela.size else 0.0,
        },
        luminous={
            "flux_lm": float(luminous_flux_lm) if luminous_flux_lm is not None else None,
            "width_m": float(luminous_width_m) if luminous_width_m is not None else None,
            "length_m": float(luminous_length_m) if luminous_length_m is not None else None,
        },
        sanity={
            "angles_nonempty": bool(c_angles.size and g_angles.size),
            "candela_nonempty": bool(candela.size),
            "candela_has_negative": bool(candela.size and np.min(candela) < 0.0),
            "candela_has_nan_or_inf": bool(candela.size and (np.isnan(candela).any() or np.isinf(candela).any())),
            "candela_all_zero": bool(candela.size and np.max(candela) == 0.0),
        },
        warnings=warnings,
    )


def verify_photometry_file(path: str, fmt: Optional[str] = None) -> PhotometryVerifyResult:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Photometry file not found: {p}")

    format_inferred = (fmt or p.suffix.replace(".", "")).upper()
    if format_inferred == "IES":
        doc = parse_ies_text(p.read_text(encoding="utf-8", errors="replace"))
        phot = photometry_from_parsed_ies(doc)
        return _build_result(
            p,
            "IES",
            phot.system,
            phot.symmetry,
            phot.c_angles_deg,
            phot.gamma_angles_deg,
            phot.candela,
            phot.luminous_flux_lm,
            phot.luminous_width_m,
            phot.luminous_length_m,
        )

    if format_inferred == "LDT":
        doc = parse_ldt_text(p.read_text(encoding="utf-8", errors="replace"))
        phot = photometry_from_parsed_ldt(doc)
        return _build_result(
            p,
            "LDT",
            phot.system,
            phot.symmetry,
            phot.c_angles_deg,
            phot.gamma_angles_deg,
            phot.candela,
            phot.luminous_flux_lm,
            phot.luminous_width_m,
            phot.luminous_length_m,
        )

    raise ValueError(f"Unsupported photometry format: {format_inferred}")
