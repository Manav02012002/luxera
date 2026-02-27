from __future__ import annotations

from typing import Any

__all__ = [
    "Photometry",
    "TiltData",
    "photometry_from_parsed_ies",
    "photometry_from_parsed_ldt",
    "sample_intensity_cd",
    "sample_intensity_cd_world",
    "direction_to_photometric_angles",
    "angles_to_direction_type_ab",
    "world_dir_to_photometric_angles",
    "verify_photometry_file",
    "PhotometryVerifyResult",
]


def __getattr__(name: str) -> Any:
    if name in {"Photometry", "TiltData", "photometry_from_parsed_ies", "photometry_from_parsed_ldt"}:
        from luxera.photometry.model import (
            Photometry,
            TiltData,
            photometry_from_parsed_ies,
            photometry_from_parsed_ldt,
        )
        return {
            "Photometry": Photometry,
            "TiltData": TiltData,
            "photometry_from_parsed_ies": photometry_from_parsed_ies,
            "photometry_from_parsed_ldt": photometry_from_parsed_ldt,
        }[name]
    if name in {"sample_intensity_cd", "sample_intensity_cd_world", "direction_to_photometric_angles", "angles_to_direction_type_ab"}:
        from luxera.photometry.sample import (
            sample_intensity_cd,
            sample_intensity_cd_world,
            direction_to_photometric_angles,
            angles_to_direction_type_ab,
        )
        return {
            "sample_intensity_cd": sample_intensity_cd,
            "sample_intensity_cd_world": sample_intensity_cd_world,
            "direction_to_photometric_angles": direction_to_photometric_angles,
            "angles_to_direction_type_ab": angles_to_direction_type_ab,
        }[name]
    if name == "world_dir_to_photometric_angles":
        from luxera.photometry.frame import world_dir_to_photometric_angles
        return world_dir_to_photometric_angles
    if name in {"verify_photometry_file", "PhotometryVerifyResult"}:
        from luxera.photometry.verify import verify_photometry_file, PhotometryVerifyResult
        return {
            "verify_photometry_file": verify_photometry_file,
            "PhotometryVerifyResult": PhotometryVerifyResult,
        }[name]
    raise AttributeError(name)
