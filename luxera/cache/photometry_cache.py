from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from luxera.photometry.interp import PhotometryLUT


def _cache_file(cache_dir: Path, content_hash: str) -> Path:
    return cache_dir / f"{content_hash}.npz"


def save_lut_to_cache(cache_dir: str | Path, lut: "PhotometryLUT") -> Path:
    root = Path(cache_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    out = _cache_file(root, lut.content_hash)
    np.savez_compressed(
        out,
        content_hash=lut.content_hash,
        system=lut.system,
        symmetry=getattr(lut, "symmetry", "UNKNOWN"),
        angles_h_deg=np.asarray(lut.angles_h_deg, dtype=float),
        angles_v_deg=np.asarray(lut.angles_v_deg, dtype=float),
        intensity_cd=np.asarray(lut.intensity_cd, dtype=float),
    )
    return out


def load_lut_from_cache(cache_dir: str | Path, content_hash: str) -> Optional["PhotometryLUT"]:
    root = Path(cache_dir).expanduser().resolve()
    path = _cache_file(root, content_hash)
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=False)
    from luxera.photometry.interp import PhotometryLUT
    return PhotometryLUT(
        content_hash=str(data["content_hash"]),
        system=str(data["system"]),
        symmetry=(str(data["symmetry"]) if "symmetry" in data else "UNKNOWN"),
        angles_h_deg=np.asarray(data["angles_h_deg"], dtype=float),
        angles_v_deg=np.asarray(data["angles_v_deg"], dtype=float),
        intensity_cd=np.asarray(data["intensity_cd"], dtype=float),
    )
