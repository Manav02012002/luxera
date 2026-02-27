from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol


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
    LLM planner adapter.
    `plan_fn` must return a dict with `calls` and optional `rationale`.
    """

    def __init__(self, plan_fn: Optional[Any] = None, fallback: Optional[PlannerBackend] = None):
        self._plan_fn = plan_fn
        self._fallback = fallback or RuleBasedPlannerBackend()

    def plan(
        self,
        *,
        intent: str,
        project_context: Mapping[str, Any],
        tool_schemas: Mapping[str, Any],
    ) -> PlannerOutput:
        if self._plan_fn is None:
            return self._fallback.plan(intent=intent, project_context=project_context, tool_schemas=tool_schemas)
        raw = self._plan_fn(intent=intent, project_context=project_context, tool_schemas=tool_schemas)
        if not isinstance(raw, Mapping):
            return PlannerOutput(calls=[], rationale="llm:invalid_output")
        calls = [
            PlannedToolCall(tool=str(c.get("tool")), args=dict(c.get("args", {})))
            for c in raw.get("calls", [])
            if isinstance(c, Mapping)
        ]
        return PlannerOutput(calls=calls, rationale=str(raw.get("rationale", "llm")))
