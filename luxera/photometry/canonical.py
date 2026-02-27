from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Dict, Literal, Optional

import numpy as np

from luxera.photometry.model import Photometry
from luxera.models.derived import Symmetry


@dataclass(frozen=True)
class CanonicalPhotometry:
    system: Literal["C", "B", "A"]
    angles_h_deg: np.ndarray
    angles_v_deg: np.ndarray
    intensity_cd: np.ndarray  # shape [H, V]
    lamp_lumens: Optional[float]
    multiplier: float
    orientation: Dict[str, str]
    tilt_mode: str
    symmetry: Symmetry = "UNKNOWN"
    source_format: Literal["IES", "LDT", "UNKNOWN"] = "UNKNOWN"
    content_hash: str = ""


def _stable_hash_payload(
    system: str,
    angles_h: np.ndarray,
    angles_v: np.ndarray,
    intensity: np.ndarray,
    lamp_lumens: Optional[float],
    multiplier: float,
    orientation: Dict[str, str],
    tilt_mode: str,
    symmetry: str,
    source_format: str,
) -> str:
    payload = {
        "system": system,
        "angles_h_deg": [float(f"{x:.12g}") for x in angles_h.tolist()],
        "angles_v_deg": [float(f"{x:.12g}") for x in angles_v.tolist()],
        "intensity_cd": [[float(f"{v:.12g}") for v in row] for row in intensity.tolist()],
        "lamp_lumens": None if lamp_lumens is None else float(f"{float(lamp_lumens):.12g}"),
        "multiplier": float(f"{float(multiplier):.12g}"),
        "orientation": {str(k): str(v) for k, v in orientation.items()},
        "tilt_mode": str(tilt_mode),
        "symmetry": str(symmetry),
        "source_format": str(source_format),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_from_photometry(phot: Photometry, *, source_format: str = "UNKNOWN") -> CanonicalPhotometry:
    system = str(phot.system)
    if system not in {"C", "B", "A"}:
        raise ValueError(f"Unsupported photometric system: {system}")
    angles_h = np.asarray(phot.c_angles_deg, dtype=float)
    angles_v = np.asarray(phot.gamma_angles_deg, dtype=float)
    intensity = np.asarray(phot.candela, dtype=float)
    if intensity.shape != (angles_h.size, angles_v.size):
        raise ValueError(
            f"Invalid candela matrix shape: got {intensity.shape}, expected {(angles_h.size, angles_v.size)}"
        )
    orientation = {
        "luminaire_up_axis": "+Z",
        "photometric_forward_axis": "+X",
        "notes": "Type C convention: C=0 toward +X, C=90 toward +Y, nadir is -Z",
    }
    tilt_mode = phot.tilt_source if phot.tilt_source else (phot.tilt.type if phot.tilt is not None else "NONE")
    h = _stable_hash_payload(
        system=system,
        angles_h=angles_h,
        angles_v=angles_v,
        intensity=intensity,
        lamp_lumens=phot.luminous_flux_lm,
        multiplier=1.0,
        orientation=orientation,
        tilt_mode=tilt_mode,
        symmetry=str(phot.symmetry),
        source_format=source_format,
    )
    return CanonicalPhotometry(
        system=system,  # type: ignore[arg-type]
        angles_h_deg=angles_h,
        angles_v_deg=angles_v,
        intensity_cd=intensity,
        lamp_lumens=phot.luminous_flux_lm,
        multiplier=1.0,
        orientation=orientation,
        tilt_mode=tilt_mode,
        symmetry=phot.symmetry,
        source_format=(source_format if source_format in {"IES", "LDT"} else "UNKNOWN"),  # type: ignore[arg-type]
        content_hash=h,
    )
