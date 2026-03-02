from __future__ import annotations

import inspect
from typing import Any, Dict, List


def _tool_name_for_api(name: str) -> str:
    return name.replace(".", "_").replace("-", "_")


def _to_json_type(type_hint: str) -> Dict[str, Any]:
    t = str(type_hint).lower()
    if "bool" in t:
        return {"type": "boolean"}
    if "int" in t:
        return {"type": "integer"}
    if "float" in t or "number" in t:
        return {"type": "number"}
    if "list" in t or "array" in t or "tuple" in t:
        return {"type": "array", "items": {"type": "string"}}
    if "dict" in t or "object" in t:
        return {"type": "object", "additionalProperties": True}
    return {"type": "string"}


def _description_from_fn(fn: Any, fallback_name: str) -> str:
    doc = inspect.getdoc(fn) or ""
    if doc:
        first_line = doc.splitlines()[0].strip()
        if first_line:
            return first_line
    return f"Execute {fallback_name.replace('_', ' ')} tool."


def _schema_from_registered_tool(tool_name: str, spec: Any) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    required: List[str] = []

    sig = inspect.signature(spec.fn)
    schema_decl = dict(spec.schema or {}) if isinstance(spec.schema, dict) else {}
    for param_name, param in sig.parameters.items():
        if param_name in {"self", "project", "approved"}:
            continue
        decl = schema_decl.get(param_name, "str")
        props[param_name] = _to_json_type(str(decl))
        if param.default is inspect.Signature.empty:
            required.append(param_name)

    return {
        "name": _tool_name_for_api(tool_name),
        "description": _description_from_fn(spec.fn, tool_name),
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": sorted(set(required)),
            "additionalProperties": False,
        },
        "x-actual_tool": tool_name,
    }


def _required_alias_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "project_open",
            "description": "Open a project file.",
            "input_schema": {
                "type": "object",
                "properties": {"project_path": {"type": "string"}},
                "required": ["project_path"],
                "additionalProperties": False,
            },
            "x-actual_tool": "project.open",
        },
        {
            "name": "project_save",
            "description": "Save current project.",
            "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "x-actual_tool": "project.save",
        },
        {
            "name": "project_grid_add",
            "description": "Add a calculation grid.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "elevation": {"type": "number"},
                    "nx": {"type": "integer"},
                    "ny": {"type": "integer"},
                },
                "required": ["name", "width", "height", "elevation", "nx", "ny"],
                "additionalProperties": False,
            },
            "x-actual_tool": "project.grid.add",
        },
        {
            "name": "geom_import",
            "description": "Import geometry file.",
            "input_schema": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}, "format": {"type": "string"}},
                "required": ["file_path"],
                "additionalProperties": False,
            },
            "x-actual_tool": "geom.import",
        },
        {
            "name": "geom_clean",
            "description": "Clean geometry and optionally detect rooms.",
            "input_schema": {
                "type": "object",
                "properties": {"detect_rooms": {"type": "boolean"}},
                "required": [],
                "additionalProperties": False,
            },
            "x-actual_tool": "geom.clean",
        },
        {
            "name": "luminaire_place",
            "description": "Place a luminaire.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                    "aim_yaw": {"type": "number"},
                },
                "required": ["asset_id", "x", "y", "z"],
                "additionalProperties": False,
            },
            "x-actual_tool": "place_luminaire",
        },
        {
            "name": "luminaire_array",
            "description": "Place a rectangular luminaire array.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "rows": {"type": "integer"},
                    "cols": {"type": "integer"},
                    "spacing_x": {"type": "number"},
                    "spacing_y": {"type": "number"},
                    "start_x": {"type": "number"},
                    "start_y": {"type": "number"},
                    "height": {"type": "number"},
                },
                "required": ["asset_id", "rows", "cols"],
                "additionalProperties": False,
            },
            "x-actual_tool": "array_luminaires",
        },
        {
            "name": "calc_run",
            "description": "Run lighting calculation for a job.",
            "input_schema": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
            "x-actual_tool": "job.run",
        },
        {
            "name": "compliance_check",
            "description": "Check EN 12464 compliance summary.",
            "input_schema": {
                "type": "object",
                "properties": {"activity_type": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
            "x-actual_tool": "compare_to_target",
        },
        {
            "name": "report_generate",
            "description": "Generate a report artifact.",
            "input_schema": {
                "type": "object",
                "properties": {"output_path": {"type": "string"}, "style": {"type": "string"}},
                "required": ["output_path"],
                "additionalProperties": False,
            },
            "x-actual_tool": "generate_report",
        },
        {
            "name": "optim_search",
            "description": "Run optimization search.",
            "input_schema": {
                "type": "object",
                "properties": {"constraints": {"type": "object", "additionalProperties": True}, "top_n": {"type": "integer"}},
                "required": [],
                "additionalProperties": False,
            },
            "x-actual_tool": "optim.search",
        },
    ]


def build_tool_schemas_from_registry(registry: "AgentToolRegistry") -> List[Dict[str, Any]]:
    """
    Convert the AgentToolRegistry into Anthropic API tool schemas.

    For each registered tool, generate:
    {
        "name": tool_name (dots replaced with underscores for API compatibility),
        "description": tool description,
        "input_schema": {
            "type": "object",
            "properties": { ... parameter definitions ... },
            "required": [ ... ]
        }
    }

    The tool descriptions and parameter schemas should be derived from
    the tool's docstring and type annotations. For tools without proper
    annotations, generate reasonable schemas from the tool name and
    known Luxera conventions.
    """
    schemas: List[Dict[str, Any]] = []

    # registry._tools contains full ToolSpec objects (fn/schema/permission tag).
    tools = getattr(registry, "_tools", {})
    if isinstance(tools, dict):
        for tool_name in sorted(tools.keys()):
            spec = tools[tool_name]
            schemas.append(_schema_from_registered_tool(tool_name, spec))

    existing_names = {s.get("name") for s in schemas if isinstance(s, dict)}
    for required in _required_alias_schemas():
        if required["name"] not in existing_names:
            schemas.append(required)

    return schemas
