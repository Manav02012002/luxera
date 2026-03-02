from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from luxera.agent.planner import PlannerOutput, PlannedToolCall
from luxera.agent.runtime import AgentRuntime, RuntimeResponse
from luxera.ai.tool_schemas import build_tool_schemas_from_registry
from luxera.project.io import load_project_schema


@dataclass
class ConversationTurn:
    role: str
    content: str
    tool_calls: List[Dict[str, Any]]
    results_summary: Optional[str]
    timestamp: str


@dataclass
class DesignConstraints:
    """Accumulated design constraints from conversation."""

    target_illuminance: Optional[float] = None
    target_uniformity: Optional[float] = None
    target_ugr: Optional[float] = None
    standard: Optional[str] = None
    activity_type: Optional[str] = None
    preferred_manufacturer: Optional[str] = None
    budget_constraint: Optional[str] = None
    room_description: Optional[str] = None


class _StaticPlanner:
    def __init__(self, calls: List[PlannedToolCall], rationale: str):
        self._calls = list(calls)
        self._rationale = rationale

    def plan(self, *, intent: str, project_context: Dict[str, Any], tool_schemas: Dict[str, Any]) -> PlannerOutput:
        return PlannerOutput(calls=list(self._calls), rationale=self._rationale)


class ConversationEngine:
    """
    Multi-turn conversation engine for the Luxera AI copilot.
    Maintains conversation history, extracts and accumulates design
    constraints, and injects context into each LLM call.
    """

    def __init__(self, project_path: str, llm_client: Optional["LLMClient"] = None):
        self.project_path = project_path
        self.llm = llm_client
        self.history: List[ConversationTurn] = []
        self.constraints = DesignConstraints()
        self._max_history_turns = 20

    def process_message(self, user_message: str) -> str:
        """
        Process a user message and return the assistant's response.
        """
        now = self._now_iso()
        self.history.append(
            ConversationTurn(
                role="user",
                content=user_message,
                tool_calls=[],
                results_summary=None,
                timestamp=now,
            )
        )
        self._extract_constraints(user_message)

        project_summary = self._build_project_summary()
        constraints_json = json.dumps(asdict(self.constraints), indent=2, sort_keys=True)
        system_prompt = (
            "You are Luxera's design copilot. Use tools when needed to modify project, run calcs, "
            "and generate reports.\n\n"
            f"Project Summary:\n{project_summary}\n\n"
            f"Accumulated Constraints:\n{constraints_json}\n"
        )

        runtime_result: Optional[RuntimeResponse] = None
        tool_calls_for_turn: List[Dict[str, Any]] = []
        response_text = ""

        if self.llm is not None:
            runtime = AgentRuntime()
            anthropic_tools = build_tool_schemas_from_registry(runtime.registry)
            tool_name_map = {
                str(t.get("name", "")): str(t.get("x-actual_tool", ""))
                for t in anthropic_tools
                if isinstance(t, dict)
            }
            chat_tools = [
                {
                    "name": str(t.get("name", "")),
                    "description": str(t.get("description", "")),
                    "input_schema": dict(t.get("input_schema", {})),
                }
                for t in anthropic_tools
            ]

            messages = self._trim_history()
            try:
                resp = self.llm.chat(messages=messages, system=system_prompt, tools=chat_tools, max_tokens=1024)
                tool_use_blocks = self.llm.extract_tool_calls(resp)
                response_text = self.llm.extract_text(resp)

                if tool_use_blocks:
                    planner_calls: List[PlannedToolCall] = []
                    for tc in tool_use_blocks:
                        api_name = str(tc.get("name", ""))
                        actual_tool = tool_name_map.get(api_name, api_name.replace("_", "."))
                        args = dict(tc.get("input", {}) or {})
                        planner_calls.append(PlannedToolCall(tool=actual_tool, args=args))

                    tool_calls_for_turn = [
                        {"tool": c.tool, "args": dict(c.args)} for c in planner_calls
                    ]
                    planner = _StaticPlanner(planner_calls, "Conversation LLM selected tool sequence.")
                    exec_runtime = AgentRuntime(planner=planner)
                    runtime_result = exec_runtime.execute(
                        self.project_path,
                        user_message,
                        approvals={"apply_diff": True, "run_job": True},
                    )
                    result_summary = self._summarize_runtime_result(runtime_result)

                    if not response_text:
                        response_text = result_summary
                    elif runtime_result.warnings:
                        followup_messages = [
                            {"role": "user", "content": user_message},
                            {
                                "role": "assistant",
                                "content": (
                                    f"Tool execution summary:\n{result_summary}\n\n"
                                    "Provide a concise user-facing update and next best action."
                                ),
                            },
                        ]
                        try:
                            follow = self.llm.chat(
                                messages=followup_messages,
                                system=system_prompt,
                                tools=chat_tools,
                                max_tokens=512,
                            )
                            follow_text = self.llm.extract_text(follow)
                            if follow_text:
                                response_text = follow_text
                        except Exception:
                            pass
                elif not response_text:
                    response_text = "I reviewed your request but did not identify an actionable tool sequence yet."
            except Exception as e:
                runtime = AgentRuntime()
                runtime_result = runtime.execute(
                    self.project_path,
                    user_message,
                    approvals={"apply_diff": True, "run_job": True},
                )
                response_text = (
                    "LLM planning unavailable; executed fallback workflow. "
                    f"{self._summarize_runtime_result(runtime_result)} (reason: {e})"
                )
                tool_calls_for_turn = [
                    c for c in (runtime_result.session_log.tool_calls if runtime_result.session_log else []) if isinstance(c, dict)
                ]
        else:
            runtime = AgentRuntime()
            runtime_result = runtime.execute(
                self.project_path,
                user_message,
                approvals={"apply_diff": True, "run_job": True},
            )
            response_text = self._summarize_runtime_result(runtime_result)
            tool_calls_for_turn = [
                c for c in (runtime_result.session_log.tool_calls if runtime_result.session_log else []) if isinstance(c, dict)
            ]

        turn_summary = self._summarize_runtime_result(runtime_result) if runtime_result is not None else None
        self.history.append(
            ConversationTurn(
                role="assistant",
                content=response_text,
                tool_calls=tool_calls_for_turn,
                results_summary=turn_summary,
                timestamp=self._now_iso(),
            )
        )
        return response_text

    def _extract_constraints(self, message: str):
        """
        Parse common constraint patterns from natural language.
        """
        txt = message.lower()

        m_lux = re.search(r"\b(\d+(?:\.\d+)?)\s*lux\b", txt)
        if m_lux:
            self.constraints.target_illuminance = float(m_lux.group(1))

        m_ugr = re.search(r"\bugr\s*(?:must\s*be\s*)?(?:below|under|<=|<|max(?:imum)?)\s*(\d+(?:\.\d+)?)", txt)
        if not m_ugr:
            m_ugr = re.search(r"\bugr\s*(\d+(?:\.\d+)?)", txt)
        if m_ugr:
            self.constraints.target_ugr = float(m_ugr.group(1))

        m_u0 = re.search(r"\buniformity\s*(?:of|>=|>|=|target)?\s*(\d+(?:\.\d+)?)", txt)
        if m_u0:
            self.constraints.target_uniformity = float(m_u0.group(1))

        if "en 12464" in txt or "en12464" in txt:
            self.constraints.standard = "EN 12464-1"

        if "office" in txt:
            self.constraints.activity_type = "OFFICE_GENERAL"
        elif "classroom" in txt:
            self.constraints.activity_type = "EDUCATION_CLASSROOM"
        elif "warehouse" in txt:
            self.constraints.activity_type = "WAREHOUSE"

        m_budget = re.search(r"\b(?:budget|cap)\s*(?:is|of|to)?\s*\$?([\d,]+(?:\.\d+)?)", txt)
        if m_budget:
            self.constraints.budget_constraint = m_budget.group(1).replace(",", "")

        m_room = re.search(r"\b(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*m\b", txt)
        if m_room:
            self.constraints.room_description = f"{m_room.group(1)}x{m_room.group(2)} m"

        m_manufacturer = re.search(r"\b(?:manufacturer|brand)\s*(?:is|:)?\s*([a-z0-9_\- ]{2,40})", txt)
        if m_manufacturer:
            self.constraints.preferred_manufacturer = m_manufacturer.group(1).strip().upper()

    def _build_project_summary(self) -> str:
        """
        Load current project and return a concise summary.
        """
        p = load_project_schema(Path(self.project_path).expanduser().resolve())
        room_lines = []
        for r in p.geometry.rooms[:8]:
            room_lines.append(f"{r.id}:{r.name} {r.width:.2f}x{r.length:.2f}x{r.height:.2f}m")

        lum_assets: Dict[str, int] = {}
        for lum in p.luminaires:
            lum_assets[lum.photometry_asset_id] = lum_assets.get(lum.photometry_asset_id, 0) + 1
        lum_text = ", ".join(f"{aid} x{count}" for aid, count in sorted(lum_assets.items())) if lum_assets else "none"

        last_result = p.results[-1] if p.results else None
        last_result_text = "none"
        compliance_text = "unknown"
        if last_result is not None:
            summary = last_result.summary if isinstance(last_result.summary, dict) else {}
            mean_lux = summary.get("mean_lux", summary.get("avg_lux", "-"))
            u0 = summary.get("uniformity_ratio", summary.get("u0", "-"))
            status = summary.get("status", "-")
            last_result_text = f"job={last_result.job_id}, mean_lux={mean_lux}, u0={u0}, status={status}"
            comp = summary.get("compliance")
            compliance_text = str(comp) if comp is not None else compliance_text

        text = [
            f"Project: {p.name}",
            f"Rooms: {len(p.geometry.rooms)}",
            f"Room Details: {'; '.join(room_lines) if room_lines else 'none'}",
            f"Luminaires: {len(p.luminaires)} ({lum_text})",
            f"Grids: {len(p.grids)}",
            f"Last Results: {last_result_text}",
            f"Compliance: {compliance_text}",
        ]
        return "\n".join(text)

    def _trim_history(self) -> List[Dict[str, str]]:
        """
        Convert history to API message format, keeping last N turns.
        """
        if len(self.history) <= self._max_history_turns:
            return [{"role": t.role, "content": t.content} for t in self.history]

        older = self.history[: len(self.history) - self._max_history_turns]
        newer = self.history[-self._max_history_turns :]

        highlights = []
        for t in older[-8:]:
            if t.role == "user":
                highlights.append(f"User: {t.content}")
            else:
                highlights.append(f"Assistant: {t.content}")
        summary_msg = "Earlier in this conversation:\n" + "\n".join(highlights)
        out = [{"role": "assistant", "content": summary_msg}]
        out.extend({"role": t.role, "content": t.content} for t in newer)
        return out

    def save_session(self, path: Path):
        """Save conversation history + constraints to JSON file."""
        payload = {
            "project_path": self.project_path,
            "constraints": asdict(self.constraints),
            "history": [asdict(t) for t in self.history],
        }
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load_session(self, path: Path):
        """Load conversation history + constraints from JSON file."""
        p = Path(path).expanduser().resolve()
        payload = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid conversation session payload")

        c = payload.get("constraints", {})
        if not isinstance(c, dict):
            c = {}
        self.constraints = DesignConstraints(**{k: c.get(k) for k in asdict(DesignConstraints()).keys()})

        loaded_history: List[ConversationTurn] = []
        for row in payload.get("history", []):
            if not isinstance(row, dict):
                continue
            loaded_history.append(
                ConversationTurn(
                    role=str(row.get("role", "assistant")),
                    content=str(row.get("content", "")),
                    tool_calls=list(row.get("tool_calls", []) or []),
                    results_summary=row.get("results_summary"),
                    timestamp=str(row.get("timestamp", self._now_iso())),
                )
            )
        self.history = loaded_history

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _summarize_runtime_result(runtime_result: Optional[RuntimeResponse]) -> str:
        if runtime_result is None:
            return "No tool execution performed."
        tool_count = len(runtime_result.session_log.tool_calls) if runtime_result.session_log else 0
        warnings = "; ".join(runtime_result.warnings) if runtime_result.warnings else "none"
        produced = ", ".join([p for p in runtime_result.produced_artifacts if p]) or "none"
        return (
            f"Executed {tool_count} tool call(s). "
            f"Artifacts: {produced}. "
            f"Warnings: {warnings}."
        )
