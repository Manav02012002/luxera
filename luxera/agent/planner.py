from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol

from luxera.ai.llm_client import LLMClient


@dataclass(frozen=True)
class PlannedToolCall:
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerOutput:
    calls: List[PlannedToolCall] = field(default_factory=list)
    rationale: str = ""


class PlannerBackend(Protocol):
    def plan(
        self,
        *,
        intent: str,
        project_context: Mapping[str, Any],
        tool_schemas: Mapping[str, Any],
    ) -> PlannerOutput:
        ...


class RuleBasedPlannerBackend:
    """
    Deterministic planner used as default backend.
    It generates ordered tool calls from intent + compact project context.
    """

    def plan(
        self,
        *,
        intent: str,
        project_context: Mapping[str, Any],
        tool_schemas: Mapping[str, Any],
    ) -> PlannerOutput:
        lintent = intent.strip().lower()
        calls: List[PlannedToolCall] = []

        import_path = self._extract_import_path(intent)
        if import_path and "detect" in lintent and "grid" in lintent:
            calls.append(PlannedToolCall("geom.import", {"file_path": import_path}))
            calls.append(PlannedToolCall("geom.clean", {"detect_rooms": True}))
            elevation, spacing = self._extract_grid_numbers(lintent)
            calls.append(
                PlannedToolCall(
                    "project.grid.add",
                    {
                        "name": "Agent Grid",
                        "width": "$room0_width",
                        "height": "$room0_length",
                        "elevation": elevation,
                        "nx": "$grid_nx_from_spacing",
                        "ny": "$grid_ny_from_spacing",
                        "spacing": spacing,
                    },
                )
            )
        elif import_path:
            calls.append(PlannedToolCall("geom.import", {"file_path": import_path}))

        if "detect rooms" in lintent or "clean geometry" in lintent:
            calls.append(PlannedToolCall("geom.clean", {"detect_rooms": True}))

        if lintent.startswith("/grid") or "grid workplane" in lintent:
            elevation, spacing = self._extract_grid_numbers(lintent)
            calls.append(
                PlannedToolCall(
                    "project.grid.add",
                    {
                        "name": "Agent Grid",
                        "width": "$room0_width",
                        "height": "$room0_length",
                        "elevation": elevation,
                        "nx": "$grid_nx_from_spacing",
                        "ny": "$grid_ny_from_spacing",
                        "spacing": spacing,
                    },
                )
            )

        if "design solve" in lintent or ("hit" in lintent and "lux" in lintent):
            calls.append(
                PlannedToolCall(
                    "propose_optimizations",
                    {
                        "job_id": "$first_job_id",
                        "constraints": "$design_constraints",
                        "top_n": 5,
                    },
                )
            )
            calls.append(
                PlannedToolCall(
                    "optim.option_diff",
                    {
                        "option": "$selected_optimization_option",
                    },
                )
            )
            calls.append(PlannedToolCall("project.diff.apply", {"diff": "$latest_diff"}))
            if "run" in lintent:
                calls.append(PlannedToolCall("job.run", {"job_id": "$first_job_id"}))

        if "optimizer" in lintent or ("optimize" in lintent and "design solve" not in lintent):
            calls.append(
                PlannedToolCall(
                    "optim.search",
                    {
                        "job_id": "$first_job_id",
                        "constraints": {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0},
                        "max_rows": 4,
                        "max_cols": 4,
                        "top_n": 8,
                    },
                )
            )
            calls.append(PlannedToolCall("project.diff.apply", {"diff": "$latest_diff"}))

        if "try" in lintent and "option" in lintent:
            calls.append(
                PlannedToolCall(
                    "optim.optimizer",
                    {
                        "job_id": "$first_job_id",
                        "candidate_limit": self._extract_first_int(lintent, default=12),
                        "constraints": {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0},
                    },
                )
            )

        if ("place" in lintent or "layout" in lintent or "target" in lintent) and "design solve" not in lintent:
            calls.append(
                PlannedToolCall(
                    "project.diff.propose_layout",
                    {
                        "target_lux": self._extract_target_lux(lintent),
                        "constraints": {"max_rows": 6, "max_cols": 6},
                    },
                )
            )
            calls.append(PlannedToolCall("project.diff.apply", {"diff": "$latest_diff"}))

        if "run" in lintent and "report" not in lintent and "design solve" not in lintent:
            calls.append(PlannedToolCall("job.run", {"job_id": "$first_job_id"}))

        if "report" in lintent:
            if "roadway" in lintent:
                calls.append(
                    PlannedToolCall(
                        "report.roadway.html",
                        {"job_id": "$latest_result_job_id", "out_html": "$roadway_report_html_path"},
                    )
                )
            if "client" in lintent:
                calls.append(
                    PlannedToolCall(
                        "bundle.client",
                        {"job_id": "$latest_result_job_id", "out_zip": "$client_bundle_path"},
                    )
                )
            if "audit" in lintent or "debug" in lintent:
                calls.append(
                    PlannedToolCall(
                        "bundle.audit",
                        {"job_id": "$latest_result_job_id", "out_zip": "$audit_bundle_path"},
                    )
                )
            if all(k not in lintent for k in ("roadway", "client", "audit", "debug")):
                calls.append(
                    PlannedToolCall(
                        "report.pdf",
                        {
                            "job_id": "$latest_result_job_id",
                            "report_type": "en12464",
                            "out_path": "$en12464_pdf_path",
                        },
                    )
                )

        if "heatmap" in lintent:
            calls.append(PlannedToolCall("results.heatmap", {"job_id": "$latest_result_job_id"}))

        if "summarize" in lintent or "summary" in lintent:
            calls.append(PlannedToolCall("results.summarize", {"job_id": "$latest_result_job_id"}))

        return PlannerOutput(calls=calls, rationale="Deterministic planner from intent/context/tool schemas.")

    @staticmethod
    def _extract_first_int(text: str, default: int) -> int:
        for tok in text.replace(",", " ").split():
            try:
                v = int(tok)
            except ValueError:
                continue
            if v > 0:
                return v
        return default

    @staticmethod
    def _extract_target_lux(text: str) -> float:
        tokens = text.replace("/", " ").split()
        for i, tok in enumerate(tokens):
            if tok.endswith("lux"):
                try:
                    return float(tok[:-3])
                except ValueError:
                    pass
            if tok == "lux" and i > 0:
                try:
                    return float(tokens[i - 1])
                except ValueError:
                    pass
            try:
                v = float(tok)
            except ValueError:
                continue
            if v >= 50.0:
                return v
        return 500.0

    @staticmethod
    def _extract_grid_numbers(text: str) -> tuple[float, float]:
        nums: List[float] = []
        for tok in text.replace(",", " ").split():
            try:
                nums.append(float(tok))
            except ValueError:
                continue
        elevation = nums[0] if len(nums) >= 1 else 0.8
        spacing = nums[1] if len(nums) >= 2 else 0.25
        spacing = max(0.1, spacing)
        return elevation, spacing

    @staticmethod
    def _extract_import_path(intent: str) -> Optional[str]:
        parts = intent.strip().split()
        for i, tok in enumerate(parts):
            if tok.lower() == "import" and i + 1 < len(parts):
                return parts[i + 1]
        return None


class MockPlannerBackend:
    """
    Deterministic canned planner for tests.
    `plans` may use exact-intent keys or substring keys.
    """

    def __init__(self, plans: Optional[Mapping[str, Mapping[str, Any]]] = None):
        self._plans = dict(plans or {})

    def plan(
        self,
        *,
        intent: str,
        project_context: Mapping[str, Any],
        tool_schemas: Mapping[str, Any],
    ) -> PlannerOutput:
        exact = self._plans.get(intent)
        if exact is None:
            lintent = intent.lower()
            for key, plan in self._plans.items():
                if key.lower() in lintent:
                    exact = plan
                    break
        if exact is None:
            return PlannerOutput(calls=[], rationale="mock:no-match")

        calls = [
            PlannedToolCall(tool=str(c.get("tool")), args=dict(c.get("args", {})))
            for c in exact.get("calls", [])
            if isinstance(c, Mapping)
        ]
        return PlannerOutput(calls=calls, rationale=str(exact.get("rationale", "mock:canned")))


class LLMPlannerBackend:
    """
    LLM-powered planner that uses Claude's tool-use API to generate
    a sequence of tool calls from natural language intent.
    """

    SYSTEM_PROMPT = """You are Luxera's lighting design AI assistant.
You help lighting designers by calling tools to manipulate their project.

Current project context:
{context}

When the user describes what they want, determine which tools to call
and in what order. Call tools directly — do not ask clarifying questions
unless the intent is truly ambiguous.

Common workflows:
- "Design an office" -> import/create room -> place luminaires -> add grid -> run calculation -> check compliance
- "Check compliance" -> calc_run -> compliance_check
- "Generate report" -> report_generate
- "The corner is too dark" -> analyze results -> luminaire_place or luminaire_array to add light
- "Try a different product" -> swap photometry asset -> calc_run -> compare results
"""

    def __init__(self, client: Optional[LLMClient] = None, fallback: Optional[PlannerBackend] = None):
        self._client = client
        self._fallback = fallback or RuleBasedPlannerBackend()

    def plan(
        self,
        *,
        intent: str,
        project_context: Mapping[str, Any],
        tool_schemas: Mapping[str, Any],
    ) -> PlannerOutput:
        # If client was not injected, create lazily only when an API key is available.
        client = self._client
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return self._fallback.plan(intent=intent, project_context=project_context, tool_schemas=tool_schemas)
            try:
                client = LLMClient()
            except ValueError:
                return self._fallback.plan(intent=intent, project_context=project_context, tool_schemas=tool_schemas)

        try:
            context_json = json.dumps(dict(project_context), indent=2, sort_keys=True, default=str)
        except Exception:
            context_json = str(project_context)

        system_prompt = self.SYSTEM_PROMPT.format(context=context_json)
        anthropic_tools, name_map = self._anthropic_tools(tool_schemas)

        try:
            response = client.chat(
                messages=[{"role": "user", "content": intent}],
                system=system_prompt,
                tools=anthropic_tools,
                max_tokens=1024,
            )
            raw_calls = client.extract_tool_calls(response)
            rationale = client.extract_text(response) or "LLM planner generated tool sequence."
        except Exception:
            return self._fallback.plan(intent=intent, project_context=project_context, tool_schemas=tool_schemas)

        calls: List[PlannedToolCall] = []
        for c in raw_calls:
            tool_api_name = str(c.get("name", ""))
            raw_tool_name = name_map.get(tool_api_name, tool_api_name.replace("_", "."))
            tool_name = self._resolve_tool_name(raw_tool_name)
            normalized_args = self._normalize_args(tool_name, dict(c.get("input", {}) or {}))
            calls.append(PlannedToolCall(tool=tool_name, args=normalized_args))

        return PlannerOutput(calls=calls, rationale=rationale)

    @staticmethod
    def _anthropic_tools(tool_schemas: Mapping[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
        tools: List[Dict[str, Any]] = []
        name_map: Dict[str, str] = {}
        for tool_name, schema in tool_schemas.items():
            if not isinstance(schema, Mapping):
                continue
            api_name = str(tool_name).replace(".", "_").replace("-", "_")
            name_map[api_name] = str(tool_name)
            tools.append(
                {
                    "name": api_name,
                    "description": f"Run Luxera tool {tool_name}",
                    "input_schema": {
                        "type": "object",
                        "properties": dict(schema.get("properties", {})) if isinstance(schema.get("properties"), Mapping) else {},
                        "required": list(schema.get("required", [])) if isinstance(schema.get("required"), list) else [],
                        "additionalProperties": False,
                    },
                }
            )
        return tools, name_map

    @staticmethod
    def _normalize_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # Bridge common alias forms to the runtime tool surface.
        if tool_name in {"geom.import", "geom_import"} and "format" in args and "fmt" not in args:
            args["fmt"] = args.pop("format")
        if tool_name in {"job.run", "calc.run", "calc_run"} and "job_id" not in args:
            args["job_id"] = "$first_job_id"
        return args

    @staticmethod
    def _resolve_tool_name(tool_name: str) -> str:
        alias_map = {
            "project_open": "project.open",
            "project_save": "project.save",
            "project_grid_add": "project.grid.add",
            "geom_import": "geom.import",
            "geom_clean": "geom.clean",
            "luminaire_place": "place_luminaire",
            "luminaire_array": "array_luminaires",
            "calc_run": "job.run",
            "compliance_check": "compare_to_target",
            "report_generate": "generate_report",
            "optim_search": "optim.search",
        }
        return alias_map.get(tool_name, tool_name)
