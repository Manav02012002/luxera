from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable[..., Any]
    schema: Dict[str, Any]
    permission_tag: str


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, name: str, fn: Callable[..., Any], *, schema: Dict[str, Any], permission_tag: str) -> None:
        self._tools[name] = ToolSpec(name=name, fn=fn, schema=schema, permission_tag=permission_tag)

    def call(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        spec = self._tools.get(tool_name)
        if spec is None:
            raise KeyError(f"Tool not registered: {tool_name}")
        return spec.fn(*args, **kwargs)

    def describe(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "schema": spec.schema,
                "permission_tag": spec.permission_tag,
            }
            for name, spec in self._tools.items()
        }

    def json_schemas(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for name, spec in self._tools.items():
            props: Dict[str, Any] = {}
            required: list[str] = []
            sig = inspect.signature(spec.fn)
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                declared = spec.schema.get(param_name, "str")
                if declared == "Project":
                    prop: Dict[str, Any] = {}
                else:
                    prop = {"type": "string"}
                if param.default is not inspect.Signature.empty:
                    if isinstance(param.default, (str, int, float, bool)) or param.default is None:
                        prop["default"] = param.default
                else:
                    required.append(param_name)
                props[param_name] = prop
            out[name] = {
                "type": "object",
                "title": name,
                "additionalProperties": False,
                "properties": props,
                "required": sorted(required),
            }
        return out


def build_default_registry(tools) -> AgentToolRegistry:
    r = AgentToolRegistry()
    r.register("context.load", tools.load_context_memory, schema={"project_path": "str"}, permission_tag="project_edit")
    r.register("context.reset", tools.reset_context_memory, schema={"project_path": "str"}, permission_tag="project_edit")
    r.register(
        "context.update",
        tools.update_context_memory,
        schema={"project": "Project", "project_path": "str", "intent": "str", "tool_calls": "list", "run_manifest": "dict"},
        permission_tag="project_edit",
    )
    r.register("project.open", tools.open_project, schema={"project_path": "str"}, permission_tag="project_edit")
    r.register("project.save", tools.save_project, schema={"project": "Project", "project_path": "Path"}, permission_tag="project_edit")
    r.register("session.save", tools.save_session_artifact, schema={"project": "Project", "runtime_id": "str", "payload": "dict"}, permission_tag="project_edit")
    r.register("project.validate", tools.validate_project, schema={"project": "Project", "job_id": "str|None"}, permission_tag="project_edit")
    r.register("project.diff.preview", tools.diff_preview, schema={"diff": "ProjectDiff"}, permission_tag="project_edit")
    r.register("project.diff.propose_layout", tools.propose_layout_diff, schema={"project": "Project", "target_lux": "float", "constraints": "dict|None"}, permission_tag="project_edit")
    r.register("optim.search", tools.optimize_layout_search, schema={"project": "Project", "job_id": "str", "constraints": "dict|None", "max_rows": "int", "max_cols": "int", "top_n": "int"}, permission_tag="run_job")
    r.register("optim.optimizer", tools.optimize_layout_candidates, schema={"project": "Project", "job_id": "str", "candidate_limit": "int", "constraints": "dict|None"}, permission_tag="run_job")
    r.register("project.diff.apply", tools.apply_diff, schema={"project": "Project", "diff": "ProjectDiff", "approved": "bool"}, permission_tag="project_edit")
    r.register("project.diff.undo", tools.undo_assistant_change, schema={"project": "Project"}, permission_tag="project_edit")
    r.register("project.diff.redo", tools.redo_assistant_change, schema={"project": "Project"}, permission_tag="project_edit")
    r.register("project.grid.add", tools.add_grid, schema={"project": "Project", "name": "str", "width": "float", "height": "float", "elevation": "float", "nx": "int", "ny": "int"}, permission_tag="project_edit")
    r.register("job.daylight.add", tools.add_daylight_job, schema={"project": "Project", "targets": "list[str]", "mode": "str", "sky": "str", "e0": "float|None", "vt": "float"}, permission_tag="project_edit")
    r.register("geom.aperture.set", tools.set_daylight_aperture, schema={"project": "Project", "opening_id": "str", "vt": "float|None"}, permission_tag="project_edit")
    r.register("geom.escape_route.add", tools.add_escape_route, schema={"project": "Project", "route_id": "str", "polyline": "list[tuple[float,float,float]]", "width_m": "float", "spacing_m": "float", "height_m": "float", "end_margin_m": "float"}, permission_tag="project_edit")
    r.register("job.emergency.add", tools.add_emergency_job, schema={"project": "Project", "routes": "list[str]", "open_area_targets": "list[str]", "standard": "str", "route_min_lux": "float", "route_u0_min": "float", "open_area_min_lux": "float", "open_area_u0_min": "float", "emergency_factor": "float"}, permission_tag="project_edit")
    r.register("variant.add", tools.add_variant, schema={"project": "Project", "variant_id": "str", "name": "str", "description": "str", "diff_ops": "list[dict]|None"}, permission_tag="project_edit")
    r.register("variant.compare", tools.compare_variants, schema={"project": "Project", "job_id": "str", "variant_ids": "list[str]", "baseline_variant_id": "str|None"}, permission_tag="run_job")
    r.register("job.run", tools.run_job, schema={"project": "Project", "job_id": "str", "approved": "bool"}, permission_tag="run_job")
    r.register("results.summarize", tools.summarize_results, schema={"project": "Project", "job_id": "str"}, permission_tag="project_edit")
    r.register("results.heatmap", tools.render_heatmap, schema={"project": "Project", "job_id": "str"}, permission_tag="project_edit")
    r.register("geom.import", tools.import_geometry, schema={"project": "Project", "file_path": "str", "fmt": "str|None"}, permission_tag="project_edit")
    r.register("geom.import_ifc", tools.import_ifc, schema={"project": "Project", "file_path": "str", "options": "dict|None"}, permission_tag="project_edit")
    r.register("geom.clean", tools.clean_geometry, schema={"project": "Project", "detect_rooms": "bool"}, permission_tag="project_edit")
    r.register("report.pdf", tools.build_pdf, schema={"project": "Project", "job_id": "str", "report_type": "str", "out_path": "str"}, permission_tag="export")
    r.register("report.roadway.html", tools.export_roadway_report, schema={"project": "Project", "job_id": "str", "out_html": "str"}, permission_tag="export")
    r.register("bundle.client", tools.export_client_bundle, schema={"project": "Project", "job_id": "str", "out_zip": "str"}, permission_tag="export")
    r.register("bundle.audit", tools.export_debug_bundle, schema={"project": "Project", "job_id": "str", "out_zip": "str"}, permission_tag="export")
    r.register("report.backend_compare", tools.export_backend_compare, schema={"project": "Project", "job_id": "str", "out_html": "str"}, permission_tag="export")
    r.register("project.summarize", tools.summarize_project_context, schema={"project": "Project"}, permission_tag="project_edit")
    r.register("create_room", tools.create_room, schema={"project": "Project", "room_id": "str", "name": "str", "width": "float", "length": "float", "height": "float", "origin": "tuple[float,float,float]", "approved": "bool"}, permission_tag="project_edit")
    r.register("edit_room", tools.edit_room, schema={"project": "Project", "room_id": "str", "updates": "dict", "approved": "bool"}, permission_tag="project_edit")
    r.register("assign_material", tools.assign_material, schema={"project": "Project", "material_id": "str", "surface_ids": "list[str]", "approved": "bool"}, permission_tag="project_edit")
    r.register("place_luminaire", tools.place_luminaire, schema={"project": "Project", "luminaire_id": "str", "name": "str", "asset_id": "str", "position": "tuple[float,float,float]", "yaw_deg": "float", "approved": "bool"}, permission_tag="project_edit")
    r.register("array_luminaires", tools.array_luminaires, schema={"project": "Project", "room_id": "str", "asset_id": "str", "rows": "int", "cols": "int", "margin_m": "float", "mount_height_m": "float", "approved": "bool"}, permission_tag="project_edit")
    r.register("aim_luminaire", tools.aim_luminaire, schema={"project": "Project", "luminaire_id": "str", "yaw_deg": "float", "approved": "bool"}, permission_tag="project_edit")
    r.register("create_grid", tools.create_grid, schema={"project": "Project", "grid_id": "str", "name": "str", "room_id": "str", "elevation_m": "float", "spacing_m": "float", "margin_m": "float", "approved": "bool"}, permission_tag="project_edit")
    r.register("update_grid", tools.update_grid, schema={"project": "Project", "grid_id": "str", "updates": "dict", "approved": "bool"}, permission_tag="project_edit")
    r.register("run_calc", tools.run_calc, schema={"project": "Project", "job_id": "str", "approved": "bool"}, permission_tag="run_job")
    r.register("generate_report", tools.generate_report, schema={"project": "Project", "job_id": "str", "out_path": "str", "report_type": "str"}, permission_tag="export")
    r.register("compare_to_target", tools.compare_to_target, schema={"project": "Project", "job_id": "str", "thresholds": "dict|None"}, permission_tag="project_edit")
    r.register("propose_optimizations", tools.propose_optimizations, schema={"project": "Project", "job_id": "str", "constraints": "dict|None", "top_n": "int"}, permission_tag="run_job")
    r.register("optim.option_diff", tools.optimization_option_diff, schema={"project": "Project", "option": "dict"}, permission_tag="project_edit")
    return r
