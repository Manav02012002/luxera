from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from luxera.models.derived import Symmetry
from luxera.models.tilt import TiltData as TiltSeriesData
from luxera.parser.ies_parser import ParsedIES
from luxera.parser.ldt_parser import ParsedLDT
from luxera.derived.metrics import infer_symmetry


PhotometricSystem = Literal["C", "B", "A"]


@dataclass(frozen=True)
class TiltData:
    type: Literal["NONE", "INCLUDE", "FILE"]
    angles_deg: Optional[np.ndarray] = None
    factors: Optional[np.ndarray] = None
    source_file: Optional[str] = None
    lamp_to_luminaire_geometry: Optional[str] = None

    def to_series(self) -> Optional[TiltSeriesData]:
        if self.angles_deg is None or self.factors is None:
            return None
        s = TiltSeriesData(angles_deg=[float(x) for x in self.angles_deg], factors=[float(x) for x in self.factors])
        s.validate()
        return s


@dataclass(frozen=True)
class Photometry:
    system: PhotometricSystem
    c_angles_deg: np.ndarray
    gamma_angles_deg: np.ndarray
    candela: np.ndarray  # shape: [num_c][num_gamma]
    luminous_flux_lm: Optional[float]
    symmetry: Symmetry
    tilt: Optional[TiltData] = None
    tilt_source: Literal["NONE", "INCLUDE", "FILE"] = "NONE"
    tilt_file: Optional[str] = None
    tilt_applied_angle: Literal["gamma"] = "gamma"
    luminous_width_m: Optional[float] = None
    luminous_length_m: Optional[float] = None
    luminous_height_m: Optional[float] = None
    ies_units_type: Optional[int] = None


def photometry_from_parsed_ies(doc: ParsedIES) -> Photometry:
    if doc.photometry is None or doc.angles is None or doc.candela is None:
        raise ValueError("Parsed IES does not include full photometry")

    system = {1: "C", 2: "B", 3: "A"}.get(doc.photometry.photometric_type)
    if system is None:
        raise ValueError(f"Unsupported photometric type: {doc.photometry.photometric_type}")

    c_angles = np.array(doc.angles.horizontal_deg, dtype=float)
    gamma_angles = np.array(doc.angles.vertical_deg, dtype=float)
    candela = np.array(doc.candela.values_cd_scaled, dtype=float)

    lumens = doc.photometry.num_lamps * doc.photometry.lumens_per_lamp
    symmetry = infer_symmetry(list(c_angles))

    tilt = None
    tilt_source: Literal["NONE", "INCLUDE", "FILE"] = "NONE"
    tilt_file: Optional[str] = None
    if doc.tilt_line is not None:
        tilt_type = (doc.tilt_mode or doc.tilt_line.split("=", 1)[1].strip().upper())
        if tilt_type == "INCLUDE" and doc.tilt_data is not None:
            tilt_source = "INCLUDE"
            tilt = TiltData(
                type="INCLUDE",
                angles_deg=np.array(doc.tilt_data[0], dtype=float),
                factors=np.array(doc.tilt_data[1], dtype=float),
                lamp_to_luminaire_geometry=doc.tilt_lamp_to_luminaire_geometry,
            )
            # strict validation on ingest
            _ = tilt.to_series()
        elif tilt_type == "FILE":
            tilt_source = "FILE"
            tilt_file = doc.tilt_file_path
            if doc.tilt_data is not None:
                tilt = TiltData(
                    type="FILE",
                    angles_deg=np.array(doc.tilt_data[0], dtype=float),
                    factors=np.array(doc.tilt_data[1], dtype=float),
                    source_file=doc.tilt_file_path,
                    lamp_to_luminaire_geometry=doc.tilt_lamp_to_luminaire_geometry,
                )
                _ = tilt.to_series()
        elif tilt_type == "NONE":
            tilt_source = "NONE"
            tilt = TiltData(type="NONE")

    dim_scale = 1.0 if int(doc.photometry.units_type) == 2 else 0.3048
    return Photometry(
        system=system,
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        candela=candela,
        luminous_flux_lm=lumens if lumens > 0 else None,
        symmetry=symmetry,
        tilt=tilt,
        tilt_source=tilt_source,
        tilt_file=tilt_file,
        tilt_applied_angle="gamma",
        luminous_width_m=float(doc.photometry.width) * dim_scale,
        luminous_length_m=float(doc.photometry.length) * dim_scale,
        luminous_height_m=float(doc.photometry.height) * dim_scale,
        ies_units_type=int(doc.photometry.units_type),
    )


def photometry_from_parsed_ldt(doc: ParsedLDT) -> Photometry:
    c_angles = np.array(doc.angles.c_planes_deg, dtype=float)
    gamma_angles = np.array(doc.angles.g_angles_deg, dtype=float)
    candela = np.array(doc.candela.values_cd_scaled, dtype=float)

    symmetry: Symmetry = "UNKNOWN"
    if doc.header.symmetry == 0:
        symmetry = "NONE"
    elif doc.header.symmetry in (1, 2, 3):
        symmetry = "BILATERAL"
    elif doc.header.symmetry == 4:
        symmetry = "FULL"

    return Photometry(
        system="C",
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        candela=candela,
        luminous_flux_lm=None,
        symmetry=symmetry,
        tilt=None,
        luminous_width_m=doc.header.geometry.luminous_width_mm / 1000.0 if doc.header.geometry.luminous_width_mm else None,
        luminous_length_m=doc.header.geometry.luminous_length_mm / 1000.0 if doc.header.geometry.luminous_length_mm else None,
        ies_units_type=None,
    )
