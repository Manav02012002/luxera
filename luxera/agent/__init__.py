__all__ = [
    "AgentAuditEvent",
    "append_audit_event",
    "AgentRuntime",
    "RuntimeResponse",
    "RuntimeAction",
    "AgentTools",
    "ToolResult",
]


def __getattr__(name):
    if name in {"AgentAuditEvent", "append_audit_event"}:
        from luxera.agent.audit import AgentAuditEvent, append_audit_event

        return {"AgentAuditEvent": AgentAuditEvent, "append_audit_event": append_audit_event}[name]
    if name in {"AgentRuntime", "RuntimeResponse", "RuntimeAction"}:
        from luxera.agent.runtime import AgentRuntime, RuntimeResponse, RuntimeAction

        return {
            "AgentRuntime": AgentRuntime,
            "RuntimeResponse": RuntimeResponse,
            "RuntimeAction": RuntimeAction,
        }[name]
    if name in {"AgentTools", "ToolResult"}:
        from luxera.agent.tools import AgentTools, ToolResult

        return {"AgentTools": AgentTools, "ToolResult": ToolResult}[name]
    raise AttributeError(name)
