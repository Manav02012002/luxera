from __future__ import annotations

import json
import http.server
import socketserver
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from luxera.agent.runtime import AgentRuntime
from luxera.agent.summarize import summarize_project
from luxera.compliance.evaluate import evaluate_indoor
from luxera.database.library import PhotometryLibrary
from luxera.design.placement import place_array_rect
from luxera.export.pdf_report import build_project_pdf_report
from luxera.export.professional_pdf import ProfessionalReportBuilder
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


class LuxeraAPIHandler(http.server.BaseHTTPRequestHandler):
    """
    REST API handler for Luxera operations.
    """

    _projects: Dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_POST(self):
        """Route POST requests to appropriate handler."""
        try:
            body = self._read_json_body()
            path = urlparse(self.path).path
            if path == "/api/v1/project/create":
                out = self._handle_project_create(body)
                return self._json_response(200, out)
            if path == "/api/v1/project/open":
                out = self._handle_project_open(body)
                return self._json_response(200, out)
            if path == "/api/v1/luminaire/place":
                out = self._handle_luminaire_place(body)
                return self._json_response(200, out)
            if path == "/api/v1/luminaire/array":
                out = self._handle_luminaire_array(body)
                return self._json_response(200, out)
            if path == "/api/v1/calc/run":
                out = self._handle_calc_run(body)
                return self._json_response(200, out)
            if path == "/api/v1/compliance/check":
                out = self._handle_compliance_check(body)
                return self._json_response(200, out)
            if path == "/api/v1/report/generate":
                out = self._handle_report_generate(body)
                return self._json_response(200, out)
            if path == "/api/v1/agent/intent":
                out = self._handle_agent_intent(body)
                return self._json_response(200, out)
            return self._json_response(404, {"error": "not_found"})
        except ValueError as e:
            return self._json_response(400, {"error": "bad_request", "message": str(e)})
        except Exception as e:  # pragma: no cover
            return self._json_response(
                500,
                {
                    "error": "internal_error",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    def do_GET(self):
        """Route GET requests."""
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/health":
                return self._json_response(200, {"status": "ok", "version": "0.3.0"})
            if parsed.path == "/api/v1/library/search":
                qs = parse_qs(parsed.query or "")
                out = self._handle_library_search(qs)
                return self._json_response(200, out)
            return self._json_response(404, {"error": "not_found"})
        except ValueError as e:
            return self._json_response(400, {"error": "bad_request", "message": str(e)})
        except Exception as e:  # pragma: no cover
            return self._json_response(
                500,
                {
                    "error": "internal_error",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    def _json_response(self, status: int, data: Dict):
        """Send JSON response with proper headers."""
        payload = json.dumps(data, sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> Dict:
        """Read and parse JSON request body."""
        raw_len = self.headers.get("Content-Length", "0").strip()
        try:
            length = int(raw_len or "0")
        except ValueError as e:
            raise ValueError("Invalid Content-Length") from e

        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise ValueError("Malformed JSON body") from e
        if not isinstance(obj, dict):
            raise ValueError("JSON body must be an object")
        return obj

    def _handle_project_create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = str(body.get("name") or "Luxera API Project")
        rooms = body.get("rooms")
        if rooms is None or not isinstance(rooms, list) or not rooms:
            raise ValueError("rooms list is required")

        root = Path.cwd() / ".luxera" / "api_projects"
        root.mkdir(parents=True, exist_ok=True)
        project_id = uuid.uuid4().hex[:12]
        path = root / f"{project_id}.luxera"

        project = Project(name=name, root_dir=str(root))
        for i, room in enumerate(rooms):
            if not isinstance(room, dict):
                continue
            width = float(room.get("width", 6.0))
            length = float(room.get("length", 8.0))
            height = float(room.get("height", 3.0))
            origin = room.get("origin", [0.0, 0.0, 0.0])
            if not isinstance(origin, (list, tuple)) or len(origin) != 3:
                origin = [0.0, 0.0, 0.0]
            project.geometry.rooms.append(
                RoomSpec(
                    id=str(room.get("id") or f"room_{i + 1}"),
                    name=str(room.get("name") or f"Room {i + 1}"),
                    width=width,
                    length=length,
                    height=height,
                    origin=(float(origin[0]), float(origin[1]), float(origin[2])),
                )
            )

        default_ies = self._default_ies_path()
        project.photometry_assets.append(
            PhotometryAsset(
                id="default_asset",
                format="IES",
                path=str(default_ies),
                metadata={"manufacturer": "Luxera", "catalog": "API-DEFAULT", "lumens": 3600, "beam_angle_deg": 90},
            )
        )

        save_project_schema(project, path)
        self._projects[project_id] = {"path": str(path)}
        return {"project_id": project_id, "path": str(path)}

    def _handle_project_open(self, body: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = body.get("path")
        if not raw_path:
            raise ValueError("path is required")
        path = Path(str(raw_path)).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Project not found: {path}")
        project = load_project_schema(path)
        project_id = uuid.uuid4().hex[:12]
        self._projects[project_id] = {"path": str(path)}
        summary = summarize_project(project).to_dict()
        return {"project_id": project_id, "summary": summary}

    def _handle_luminaire_place(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        luminaires = body.get("luminaires")
        if not project_id:
            raise ValueError("project_id is required")
        if not isinstance(luminaires, list):
            raise ValueError("luminaires list is required")

        project, path = self._load_project_for_id(project_id)
        default_asset = project.photometry_assets[0].id if project.photometry_assets else "default_asset"
        count = 0
        for i, row in enumerate(luminaires):
            if not isinstance(row, dict):
                continue
            asset_id = str(row.get("asset_id") or default_asset)
            if not any(a.id == asset_id for a in project.photometry_assets):
                asset_id = default_asset
            x = float(row.get("x", 1.0))
            y = float(row.get("y", 1.0))
            z = float(row.get("z", 2.8))
            yaw = float(row.get("aim_yaw", row.get("yaw", 0.0)))
            lum = LuminaireInstance(
                id=str(row.get("id") or f"lum_{len(project.luminaires) + i + 1}"),
                name=str(row.get("name") or f"Luminaire {len(project.luminaires) + i + 1}"),
                photometry_asset_id=asset_id,
                transform=TransformSpec(position=(x, y, z), rotation=RotationSpec(type="euler_zyx", euler_deg=(yaw, 0.0, 0.0))),
            )
            project.luminaires.append(lum)
            count += 1
        save_project_schema(project, path)
        return {"count": count}

    def _handle_luminaire_array(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        if not project_id:
            raise ValueError("project_id is required")

        project, path = self._load_project_for_id(project_id)
        if not project.geometry.rooms:
            raise ValueError("Project has no rooms")
        room = project.geometry.rooms[0]

        rows = max(1, int(body.get("rows", 2)))
        cols = max(1, int(body.get("cols", 2)))
        margin_x = float(body.get("margin_x", 0.8))
        margin_y = float(body.get("margin_y", 0.8))
        height = float(body.get("height", room.height - 0.2))
        asset_id = str(body.get("asset_id") or (project.photometry_assets[0].id if project.photometry_assets else "default_asset"))
        if not any(a.id == asset_id for a in project.photometry_assets):
            asset_id = project.photometry_assets[0].id

        arr = place_array_rect(
            room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
            nx=cols,
            ny=rows,
            margin_x=margin_x,
            margin_y=margin_y,
            z=room.origin[2] + height,
            photometry_asset_id=asset_id,
        )
        project.luminaires = list(arr)
        save_project_schema(project, path)
        return {"count": len(project.luminaires)}

    def _handle_calc_run(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        if not project_id:
            raise ValueError("project_id is required")
        job_type = str(body.get("job_type") or "direct")
        backend = str(body.get("backend") or "cpu")

        project, path = self._load_project_for_id(project_id)
        if not project.grids and project.geometry.rooms:
            room = project.geometry.rooms[0]
            project.grids.append(
                CalcGrid(
                    id="grid_api",
                    name="API Grid",
                    origin=(room.origin[0], room.origin[1], room.origin[2]),
                    width=float(room.width),
                    height=float(room.length),
                    elevation=0.85,
                    nx=max(4, int(round(room.width / 0.5)) + 1),
                    ny=max(4, int(round(room.length / 0.5)) + 1),
                    room_id=room.id,
                )
            )
        job = next((j for j in project.jobs if j.id == "api_job"), None)
        if job is None:
            project.jobs.append(JobSpec(id="api_job", type=job_type, backend=backend, seed=0))
        else:
            job.type = job_type  # type: ignore[assignment]
            job.backend = backend  # type: ignore[assignment]

        save_project_schema(project, path)
        ref = run_job_in_memory(project, "api_job")
        save_project_schema(project, path)

        summary = dict(ref.summary or {})
        e_avg = float(summary.get("mean_lux", summary.get("avg_lux", 0.0)) or 0.0)
        e_min = float(summary.get("min_lux", 0.0) or 0.0)
        e_max = float(summary.get("max_lux", 0.0) or 0.0)
        u0 = float(summary.get("uniformity_ratio", summary.get("u0", 0.0)) or 0.0)
        return {
            "job_id": ref.job_id,
            "summary": {"E_avg": e_avg, "E_min": e_min, "E_max": e_max, "uniformity": u0},
        }

    def _handle_compliance_check(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        if not project_id:
            raise ValueError("project_id is required")
        standard = str(body.get("standard") or "EN 12464-1")
        activity_type = str(body.get("activity_type") or "OFFICE_GENERAL")

        project, _ = self._load_project_for_id(project_id)
        if not project.results:
            raise ValueError("No calculation results available")
        summary = dict(project.results[-1].summary or {})

        target_map = {
            "OFFICE_GENERAL": (500.0, 0.6),
            "EDUCATION_CLASSROOM": (300.0, 0.6),
            "RETAIL_SALES": (500.0, 0.4),
            "WAREHOUSE": (200.0, 0.4),
        }
        target_lux, target_u0 = target_map.get(activity_type.upper(), (500.0, 0.4))

        source = {
            "standard": standard,
            "activity_type": activity_type,
            "avg_lux": float(summary.get("mean_lux", summary.get("avg_lux", 0.0)) or 0.0),
            "avg_target_lux": target_lux,
            "uniformity_ratio": float(summary.get("uniformity_ratio", summary.get("u0", 0.0)) or 0.0),
            "uniformity_ratio_min": target_u0,
        }
        source["avg_ok"] = source["avg_lux"] >= source["avg_target_lux"]
        source["uo_ok"] = source["uniformity_ratio"] >= source["uniformity_ratio_min"]
        source["status"] = "PASS" if (source["avg_ok"] and source["uo_ok"]) else "FAIL"

        ev = evaluate_indoor({"compliance_profile": source})
        checks = []
        for key, value in source.items():
            if key.endswith("_ok"):
                checks.append({"name": key, "pass": bool(value)})
        return {"compliant": ev.status == "PASS", "checks": checks, "status": ev.status, "failed_checks": ev.failed_checks}

    def _handle_report_generate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        if not project_id:
            raise ValueError("project_id is required")

        style = str(body.get("style") or "standard").lower()
        output_path = body.get("output_path")
        if not output_path:
            raise ValueError("output_path is required")

        project, _ = self._load_project_for_id(project_id)
        if not project.results:
            raise ValueError("No calculation results available")
        ref = project.results[-1]

        out = Path(str(output_path)).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        if style == "professional":
            results = {
                "summary": dict(ref.summary or {}),
                "result_dir": str(ref.result_dir),
                "job_id": ref.job_id,
            }
            ProfessionalReportBuilder(project, results).build(out)
        else:
            build_project_pdf_report(project, ref, out)

        pages = self._count_pdf_pages(out)
        return {"path": str(out), "pages": pages}

    def _handle_agent_intent(self, body: Dict[str, Any]) -> Dict[str, Any]:
        project_id = str(body.get("project_id") or "")
        intent = str(body.get("intent") or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        if not intent:
            raise ValueError("intent is required")

        _, path = self._load_project_for_id(project_id)
        runtime = AgentRuntime()
        res = runtime.execute(str(path), intent, approvals={"apply_diff": True, "run_job": True})
        actions = [
            {
                "kind": a.kind,
                "requires_approval": bool(a.requires_approval),
                "payload": dict(a.payload),
            }
            for a in res.actions
        ]
        return {
            "plan": res.plan,
            "actions": actions,
            "results": {
                "run_manifest": dict(res.run_manifest),
                "warnings": list(res.warnings),
                "produced_artifacts": list(res.produced_artifacts),
            },
        }

    def _handle_library_search(self, qs: Dict[str, Any]) -> Dict[str, Any]:
        db_raw = self._q(qs, "db")
        db_path = Path(db_raw).expanduser().resolve() if db_raw else (Path.home() / ".luxera" / "photometry_library.sqlite")
        if not db_path.exists():
            return {"results": [], "total": 0}

        query = self._q(qs, "query")
        manufacturer = self._q(qs, "manufacturer")
        min_lumens = self._q_float(qs, "min_lumens")
        max_lumens = self._q_float(qs, "max_lumens")

        with PhotometryLibrary(db_path) as lib:
            rows, total = lib.search(
                query=query,
                manufacturer=manufacturer,
                min_lumens=min_lumens,
                max_lumens=max_lumens,
                limit=50,
                offset=0,
            )
        results = [
            {
                "id": r.id,
                "file_path": r.file_path,
                "manufacturer": r.manufacturer,
                "catalog_number": r.catalog_number,
                "total_lumens": r.total_lumens,
                "beam_angle_deg": r.beam_angle_deg,
            }
            for r in rows
        ]
        return {"results": results, "total": int(total)}

    @classmethod
    def _q(cls, qs: Dict[str, Any], name: str) -> str:
        vals = qs.get(name, [])
        if isinstance(vals, list) and vals:
            return str(vals[0])
        return ""

    @classmethod
    def _q_float(cls, qs: Dict[str, Any], name: str) -> float | None:
        raw = cls._q(qs, name)
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError as e:
            raise ValueError(f"Invalid float query param: {name}") from e

    def _load_project_for_id(self, project_id: str) -> tuple[Project, Path]:
        info = self._projects.get(project_id)
        if not isinstance(info, dict):
            raise ValueError(f"Unknown project_id: {project_id}")
        path = Path(str(info.get("path", ""))).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Project path missing for project_id: {project_id}")
        project = load_project_schema(path)
        return project, path

    @staticmethod
    def _count_pdf_pages(path: Path) -> int:
        data = path.read_bytes()
        import re

        return len(re.findall(rb"/Type\s*/Page\b", data))

    @staticmethod
    def _default_ies_path() -> Path:
        fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
        if fixture.exists():
            return fixture

        root = Path.cwd() / ".luxera" / "api_projects"
        root.mkdir(parents=True, exist_ok=True)
        out = root / "default.ies"
        if not out.exists():
            out.write_text(
                """IESNA:LM-63-2019
[MANUFAC] Luxera API
[LUMCAT] API-DEFAULT
TILT=NONE
1 1200 1 3 1 1 2 0.50 0.50 0.10
0 45 90
0
100 80 60
""",
                encoding="utf-8",
            )
        return out


def start_server(host: str = "0.0.0.0", port: int = 8420):
    """Start the Luxera API server."""

    class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    with _ThreadedServer((host, int(port)), LuxeraAPIHandler) as httpd:
        print(f"Luxera API server running on http://{host}:{port}")
        httpd.serve_forever()
