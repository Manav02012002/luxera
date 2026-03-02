from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from luxera.compliance.evaluate import evaluate_indoor
from luxera.database.library import PhotometryLibrary
from luxera.design.placement import place_array_rect
from luxera.export.professional_pdf import ProfessionalReportBuilder
from luxera.project.io import save_project_schema
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, PhotometryAsset, Project, RoomSpec


@dataclass(frozen=True)
class PipelineInputs:
    room_width: float
    room_length: float
    room_height: float
    target_illuminance: float
    standard: str
    activity_type: str
    floor_reflectance: float
    wall_reflectance: float
    ceiling_reflectance: float


@dataclass(frozen=True)
class PipelineResult:
    project_path: Path
    report_path: Path
    final_E_avg: float
    final_uniformity: float
    compliant: bool
    iterations: int
    luminaire_count: int


class CompliancePipeline:
    """
    Automated pipeline: natural language intent -> full compliance report.
    """

    def __init__(
        self,
        output_dir: Path,
        library_db: Optional[Path] = None,
        default_ies_path: Optional[Path] = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.library_db = Path(library_db).expanduser().resolve() if library_db else None
        self.default_ies_path = Path(default_ies_path).expanduser().resolve() if default_ies_path else None
        self._last_iterations = 0
        self._last_summary: Dict[str, Any] = {}
        self._last_ref = None

    def run(self, intent: str) -> PipelineResult:
        """Execute the full pipeline."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        inputs = self._parse_intent(intent)

        ies_path, luminaire_lumens, beam_angle, manufacturer = self._select_photometry(intent)
        if ies_path is None or not ies_path.exists():
            raise ValueError("No IES file available. Provide default_ies_path or an indexed library DB.")

        project_path = self.output_dir / "autopilot_project.luxera"
        report_path = self.output_dir / "autopilot_compliance_report.pdf"

        project = Project(name="Autopilot Compliance", root_dir=str(self.output_dir))
        room = RoomSpec(
            id="room_main",
            name="Main Space",
            width=inputs.room_width,
            length=inputs.room_length,
            height=inputs.room_height,
            floor_reflectance=inputs.floor_reflectance,
            wall_reflectance=inputs.wall_reflectance,
            ceiling_reflectance=inputs.ceiling_reflectance,
        )
        project.geometry.rooms.append(room)

        project.photometry_assets.append(
            PhotometryAsset(
                id="asset_main",
                format="IES",
                path=str(ies_path),
                metadata={
                    "manufacturer": manufacturer,
                    "lumens": float(luminaire_lumens),
                    "beam_angle_deg": float(beam_angle),
                },
            )
        )

        mount_height_m = max(2.2, inputs.room_height - 0.2)
        n_rows, n_cols, spacing_x, spacing_y = self._compute_initial_layout(
            room_width=inputs.room_width,
            room_length=inputs.room_length,
            room_height=inputs.room_height,
            target_lux=inputs.target_illuminance,
            luminaire_lumens=luminaire_lumens,
            beam_angle=beam_angle,
        )
        self._apply_array_layout(
            project,
            rows=n_rows,
            cols=n_cols,
            spacing_x=spacing_x,
            spacing_y=spacing_y,
            mount_height=mount_height_m,
            asset_id="asset_main",
        )

        grid_spacing = 0.5
        nx = max(4, int(round(inputs.room_width / grid_spacing)) + 1)
        ny = max(4, int(round(inputs.room_length / grid_spacing)) + 1)
        project.grids.append(
            CalcGrid(
                id="grid_main",
                name="Workplane Grid",
                origin=(0.0, 0.0, 0.0),
                width=inputs.room_width,
                height=inputs.room_length,
                elevation=0.85,
                nx=nx,
                ny=ny,
                room_id="room_main",
            )
        )

        project.jobs.append(JobSpec(id="job_direct", type="direct", backend="cpu", seed=0))

        save_project_schema(project, project_path)

        converged = self._iterate_to_target(project, inputs.target_illuminance, max_iterations=5)
        save_project_schema(project, project_path)

        final_avg = self._as_float(self._last_summary.get("mean_lux") or self._last_summary.get("avg_lux"))
        final_u0 = self._as_float(self._last_summary.get("uniformity_ratio") or self._last_summary.get("u0"))

        u0_target = self._uniformity_target(inputs.activity_type)
        profile = {
            "standard": inputs.standard,
            "activity_type": inputs.activity_type,
            "avg_target_lux": float(inputs.target_illuminance),
            "uniformity_ratio_min": float(u0_target),
            "avg_ok": final_avg >= float(inputs.target_illuminance),
            "uo_ok": final_u0 >= float(u0_target),
            "status": "PASS" if (final_avg >= float(inputs.target_illuminance) and final_u0 >= float(u0_target)) else "FAIL",
            "avg_lux": final_avg,
            "uniformity_ratio": final_u0,
            "iterations": self._last_iterations,
            "converged": bool(converged),
        }
        ev = evaluate_indoor({"compliance_profile": profile})
        compliant = ev.status == "PASS"

        if self._last_ref is not None:
            for ref in project.results:
                if ref.job_id == self._last_ref.job_id and ref.job_hash == self._last_ref.job_hash:
                    if not isinstance(ref.summary, dict):
                        ref.summary = {}
                    ref.summary["compliance_profile"] = dict(profile)
                    ref.summary["compliance"] = {
                        "status": ev.status,
                        "failed_checks": list(ev.failed_checks),
                        "explanations": list(ev.explanations),
                    }
                    break
            save_project_schema(project, project_path)

        report_results = {
            "summary": dict(project.results[-1].summary) if project.results else dict(self._last_summary),
            "result_dir": str(self._last_ref.result_dir) if self._last_ref is not None else "",
            "job_id": "job_direct",
            "client": "Autopilot",
        }
        ProfessionalReportBuilder(project, report_results).build(report_path)

        return PipelineResult(
            project_path=project_path,
            report_path=report_path,
            final_E_avg=final_avg,
            final_uniformity=final_u0,
            compliant=bool(compliant),
            iterations=self._last_iterations,
            luminaire_count=len(project.luminaires),
        )

    def _parse_intent(self, intent: str) -> PipelineInputs:
        """
        Extract structured inputs from natural language using regex.
        """
        txt = intent.lower()

        # Dimensions: 12x8m or 12m by 8m or 12 x 8 x 3m
        m_dims3 = re.search(r"(\d+(?:\.\d+)?)\s*(?:m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*m", txt)
        m_dims2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*m", txt)
        m_by2 = re.search(r"(\d+(?:\.\d+)?)\s*m\s*(?:by|x)\s*(\d+(?:\.\d+)?)\s*m", txt)

        if m_dims3:
            room_width = float(m_dims3.group(1))
            room_length = float(m_dims3.group(2))
            room_height = float(m_dims3.group(3))
        elif m_dims2:
            room_width = float(m_dims2.group(1))
            room_length = float(m_dims2.group(2))
            room_height = 3.0
        elif m_by2:
            room_width = float(m_by2.group(1))
            room_length = float(m_by2.group(2))
            room_height = 3.0
        else:
            room_width, room_length, room_height = 12.0, 8.0, 3.0

        m_lux = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:lux|lx)\b", txt)
        target_illuminance = float(m_lux.group(1)) if m_lux else 500.0

        standard = "EN 12464-1"
        if "cibse" in txt:
            standard = "CIBSE"
        elif "en12464" in txt or "en 12464" in txt:
            standard = "EN 12464-1"

        activity_type = "OFFICE_GENERAL"
        if "classroom" in txt or "education" in txt:
            activity_type = "EDUCATION_CLASSROOM"
        elif "retail" in txt or "shop" in txt:
            activity_type = "RETAIL_SALES"
        elif "warehouse" in txt:
            activity_type = "WAREHOUSE"
        elif "office" in txt:
            activity_type = "OFFICE_GENERAL"

        # Optional reflectance extraction: e.g. 0.2/0.5/0.7
        m_refl = re.search(r"(0\.\d+)\s*/\s*(0\.\d+)\s*/\s*(0\.\d+)", txt)
        if m_refl:
            floor_reflectance = float(m_refl.group(1))
            wall_reflectance = float(m_refl.group(2))
            ceiling_reflectance = float(m_refl.group(3))
        else:
            floor_reflectance, wall_reflectance, ceiling_reflectance = 0.2, 0.5, 0.7

        return PipelineInputs(
            room_width=room_width,
            room_length=room_length,
            room_height=room_height,
            target_illuminance=target_illuminance,
            standard=standard,
            activity_type=activity_type,
            floor_reflectance=floor_reflectance,
            wall_reflectance=wall_reflectance,
            ceiling_reflectance=ceiling_reflectance,
        )

    def _required_luminaires(self, E: float, A: float, F: float, UF: float, MF: float) -> float:
        return float(E) * float(A) / max(float(F) * float(UF) * float(MF), 1e-9)

    def _compute_initial_layout(
        self, room_width: float, room_length: float, room_height: float, target_lux: float, luminaire_lumens: float, beam_angle: float
    ) -> Tuple[int, int, float, float]:
        """
        Compute number of rows and columns and spacing using the lumen method.
        """
        area = max(room_width * room_length, 1e-6)
        hm = max(room_height - 0.85, 1.2)
        room_index = (room_width * room_length) / max(hm * (room_width + room_length), 1e-6)
        uf = max(0.35, min(0.75, 0.45 + 0.10 * math.tanh(room_index - 1.0)))
        mf = 0.80

        n_req = self._required_luminaires(target_lux, area, luminaire_lumens, uf, mf)
        n_req = max(1.0, n_req)

        cols = max(2, int(math.ceil(math.sqrt(n_req * room_width / max(room_length, 1e-6)))))
        rows = max(2, int(math.ceil(n_req / max(cols, 1))))

        spacing_x = room_width / float(cols + 1)
        spacing_y = room_length / float(rows + 1)

        # Spacing-to-height ratio limit estimated from beam angle.
        shr_limit = max(0.7, min(1.6, math.tan(math.radians(max(beam_angle, 30.0) * 0.5))))
        max_spacing = shr_limit * hm
        while spacing_x > max_spacing and cols < 20:
            cols += 1
            spacing_x = room_width / float(cols + 1)
        while spacing_y > max_spacing and rows < 20:
            rows += 1
            spacing_y = room_length / float(rows + 1)

        return rows, cols, spacing_x, spacing_y

    def _iterate_to_target(self, project, target_lux, max_iterations=5) -> bool:
        """
        Run calc, check if E_avg meets target. If too low, add luminaires.
        If too high (>150% of target), remove some. Return True if converged.
        """
        converged = False
        iterations = 0

        room = project.geometry.rooms[0]
        asset_id = project.photometry_assets[0].id if project.photometry_assets else "asset_main"
        mount_h = max(2.2, room.height - 0.2)

        rows, cols = self._infer_rows_cols(project.luminaires, room.width, room.length)
        spacing_x = room.width / float(max(cols + 1, 2))
        spacing_y = room.length / float(max(rows + 1, 2))

        for it in range(1, max_iterations + 1):
            iterations = it
            ref = run_job_in_memory(project, "job_direct")
            self._last_ref = ref
            summary = dict(ref.summary or {})
            self._last_summary = summary

            e_avg = self._as_float(summary.get("mean_lux") or summary.get("avg_lux"))
            if target_lux <= e_avg <= (1.5 * target_lux):
                converged = True
                break

            if e_avg < target_lux:
                if room.width >= room.length:
                    cols += 1
                else:
                    rows += 1
            else:  # too high
                if cols >= rows and cols > 1:
                    cols -= 1
                elif rows > 1:
                    rows -= 1

            rows = max(1, rows)
            cols = max(1, cols)
            spacing_x = room.width / float(max(cols + 1, 2))
            spacing_y = room.length / float(max(rows + 1, 2))
            self._apply_array_layout(
                project,
                rows=rows,
                cols=cols,
                spacing_x=spacing_x,
                spacing_y=spacing_y,
                mount_height=mount_h,
                asset_id=asset_id,
            )

        self._last_iterations = iterations
        return converged

    def _select_photometry(self, intent: str) -> tuple[Optional[Path], float, float, str]:
        manufacturer_hint = None
        m = re.search(r"(?:manufacturer|brand)\s*(?:is|:)?\s*([a-zA-Z0-9_\- ]{2,40})", intent)
        if m:
            manufacturer_hint = m.group(1).strip()

        if self.library_db is not None and self.library_db.exists():
            try:
                with PhotometryLibrary(self.library_db) as lib:
                    rows, _ = lib.search(manufacturer=manufacturer_hint, min_lumens=1500.0, limit=1)
                    if rows:
                        rec = rows[0]
                        return (
                            Path(rec.file_path).expanduser().resolve(),
                            float(rec.total_lumens or 3200.0),
                            float(rec.beam_angle_deg or 90.0),
                            str(rec.manufacturer or "Library"),
                        )
            except Exception:
                pass

        if self.default_ies_path is not None and self.default_ies_path.exists():
            return self.default_ies_path, 3600.0, 90.0, "Default"

        fallback = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
        if fallback.exists():
            return fallback, 3600.0, 90.0, "Luxera Synthetic"

        return None, 3600.0, 90.0, "Default"

    def _apply_array_layout(self, project: Project, rows: int, cols: int, spacing_x: float, spacing_y: float, mount_height: float, asset_id: str) -> None:
        room = project.geometry.rooms[0]
        mx = max(0.2, min(room.width * 0.2, spacing_x * 0.5))
        my = max(0.2, min(room.length * 0.2, spacing_y * 0.5))
        arr = place_array_rect(
            room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
            nx=max(1, cols),
            ny=max(1, rows),
            margin_x=float(mx),
            margin_y=float(my),
            z=float(room.origin[2] + mount_height),
            photometry_asset_id=asset_id,
        )
        for lum in arr:
            lum.mounting_height_m = float(mount_height)
            lum.maintenance_factor = 0.8
            lum.flux_multiplier = 1.0
        project.luminaires = list(arr)

    @staticmethod
    def _uniformity_target(activity_type: str) -> float:
        t = str(activity_type).upper()
        if "OFFICE" in t:
            return 0.6
        if "CLASSROOM" in t:
            return 0.6
        if "WAREHOUSE" in t:
            return 0.4
        return 0.4

    @staticmethod
    def _infer_rows_cols(luminaires: list[Any], width: float, length: float) -> tuple[int, int]:
        if not luminaires:
            return 2, 2
        xs = sorted({round(float(l.transform.position[0]), 3) for l in luminaires})
        ys = sorted({round(float(l.transform.position[1]), 3) for l in luminaires})
        cols = len(xs)
        rows = len(ys)
        if rows * cols < len(luminaires):
            n = int(round(math.sqrt(max(len(luminaires), 1))))
            cols = max(1, n)
            rows = max(1, int(math.ceil(len(luminaires) / float(cols))))
        cols = max(1, min(cols, max(1, int(width) + 4)))
        rows = max(1, min(rows, max(1, int(length) + 4)))
        return rows, cols

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0
