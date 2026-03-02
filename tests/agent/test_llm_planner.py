from __future__ import annotations

from typing import Any, Dict, List

from luxera.agent.planner import LLMPlannerBackend, PlannerOutput, RuleBasedPlannerBackend
from luxera.agent.tools.api import AgentTools
from luxera.agent.tools.registry import build_default_registry
from luxera.ai.tool_schemas import build_tool_schemas_from_registry


class MockLLMClient:
    def __init__(self, response: Dict[str, Any]):
        self._response = response

    def chat(self, messages: List[Dict[str, str]], system: str | None = None, tools: List[Dict[str, Any]] | None = None, max_tokens: int = 4096) -> Dict[str, Any]:
        assert messages
        assert isinstance(tools, list)
        return self._response

    def extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        calls: List[Dict[str, Any]] = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append({"name": str(block.get("name", "")), "input": dict(block.get("input", {}) or {})})
        return calls

    def extract_text(self, response: Dict[str, Any]) -> str:
        return "\n".join(
            str(block.get("text", ""))
            for block in response.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()


class ErrorLLMClient:
    def chat(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise ValueError("API failure")

    def extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def extract_text(self, response: Dict[str, Any]) -> str:
        return ""


def test_fallback_when_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    registry = build_default_registry(AgentTools())
    fallback = RuleBasedPlannerBackend()
    planner = LLMPlannerBackend(client=None, fallback=fallback)

    expected = fallback.plan(
        intent="generate report",
        project_context={"summary": {"rooms": 1}},
        tool_schemas=registry.json_schemas(),
    )
    got = planner.plan(
        intent="generate report",
        project_context={"summary": {"rooms": 1}},
        tool_schemas=registry.json_schemas(),
    )
    assert got == expected


def test_tool_schemas_generated() -> None:
    registry = build_default_registry(AgentTools())
    schemas = build_tool_schemas_from_registry(registry)
    assert len(schemas) >= 10
    names = {str(s.get("name", "")) for s in schemas if isinstance(s, dict)}
    required = {
        "project_open",
        "project_save",
        "project_grid_add",
        "geom_import",
        "geom_clean",
        "luminaire_place",
        "luminaire_array",
        "calc_run",
        "compliance_check",
        "report_generate",
        "optim_search",
    }
    assert required.issubset(names)


def test_schema_format_valid() -> None:
    registry = build_default_registry(AgentTools())
    schemas = build_tool_schemas_from_registry(registry)
    assert schemas
    for schema in schemas:
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema
        assert isinstance(schema["input_schema"], dict)
        assert schema["input_schema"].get("type") == "object"


def test_planner_with_mock_client() -> None:
    registry = build_default_registry(AgentTools())
    mock_response = {
        "content": [
            {"type": "text", "text": "I'll add a grid and run the first job."},
            {
                "type": "tool_use",
                "name": "project_grid_add",
                "input": {"name": "Agent Grid", "width": 6.0, "height": 8.0, "elevation": 0.8, "nx": 25, "ny": 33},
            },
            {
                "type": "tool_use",
                "name": "job_run",
                "input": {"job_id": "$first_job_id"},
            },
        ]
    }
    planner = LLMPlannerBackend(client=MockLLMClient(mock_response), fallback=RuleBasedPlannerBackend())

    out = planner.plan(
        intent="Add a grid and run",
        project_context={"summary": {"room_count": 1, "luminaire_count": 4}},
        tool_schemas=registry.json_schemas(),
    )

    assert isinstance(out, PlannerOutput)
    assert len(out.calls) == 2
    assert out.calls[0].tool == "project.grid.add"
    assert out.calls[1].tool == "job.run"
    assert "add a grid" in out.rationale.lower()


def test_planner_api_error_fallback() -> None:
    registry = build_default_registry(AgentTools())
    fallback = RuleBasedPlannerBackend()
    planner = LLMPlannerBackend(client=ErrorLLMClient(), fallback=fallback)

    expected = fallback.plan(
        intent="run and generate report",
        project_context={"summary": {}},
        tool_schemas=registry.json_schemas(),
    )
    out = planner.plan(
        intent="run and generate report",
        project_context={"summary": {}},
        tool_schemas=registry.json_schemas(),
    )
    assert out == expected
