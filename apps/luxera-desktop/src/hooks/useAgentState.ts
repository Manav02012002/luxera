import { useReducer } from "react";
import type { AgentConversationMessage, AgentDiffPreview } from "../types";
import { tauriInvoke } from "../utils/tauri";

interface AgentState {
  agentConversation: AgentConversationMessage[];
  agentLoading: boolean;
  agentError: string;
  agentDiffPreview: AgentDiffPreview | null;
  agentDiffApproved: boolean;
}

type Action = { type: "patch"; patch: Partial<AgentState> };

function reducer(state: AgentState, action: Action): AgentState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    default:
      return state;
  }
}

interface ExecuteTurnArgs {
  projectPath: string;
  intent: string;
  approvalsJson: string;
  applyDiff: boolean;
  runJob: boolean;
  selectedOptionIndex: string;
}

interface ExecuteTurnResult {
  response: Record<string, unknown>;
  approvalsJson: string;
  assistantMessage: AgentConversationMessage;
}

interface UseAgentStateArgs {
  hasTauri: boolean;
}

function parseAgentDiffPreview(response: Record<string, unknown>): AgentDiffPreview | null {
  const raw = response.diff_preview as Record<string, unknown> | undefined;
  const ops = (raw?.ops as unknown[]) ?? [];
  if (!Array.isArray(ops) || ops.length === 0) {
    return null;
  }
  const adds: AgentDiffPreview["adds"] = [];
  const removes: string[] = [];
  const moves: AgentDiffPreview["moves"] = [];

  const findNum = (payload: Record<string, unknown>, keys: string[]): number | null => {
    for (const k of keys) {
      const v = Number(payload[k]);
      if (Number.isFinite(v)) {
        return v;
      }
    }
    return null;
  };

  for (const opAny of ops) {
    if (!opAny || typeof opAny !== "object") {
      continue;
    }
    const op = opAny as Record<string, unknown>;
    const kind = String(op.kind ?? "").toLowerCase();
    const mode = String(op.op ?? "").toLowerCase();
    const id = String(op.id ?? "");
    const payload = op.payload && typeof op.payload === "object" ? (op.payload as Record<string, unknown>) : null;
    if (kind !== "luminaire") {
      continue;
    }
    if (mode === "add" && payload) {
      const pos = payload.transform && typeof payload.transform === "object" ? (payload.transform as Record<string, unknown>).position : null;
      const arr = Array.isArray(pos) ? pos : null;
      const x = arr ? Number(arr[0]) : findNum(payload, ["x", "new_x"]);
      const y = arr ? Number(arr[1]) : findNum(payload, ["y", "new_y"]);
      const z = arr ? Number(arr[2]) : findNum(payload, ["z", "new_z"]);
      if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
        adds.push({ id: id || `add_${adds.length + 1}`, x, y, z });
      }
    }
    if (mode === "remove" && id) {
      removes.push(id);
    }
    if (mode === "modify" && payload && id) {
      const oldPayload = payload.old && typeof payload.old === "object" ? (payload.old as Record<string, unknown>) : payload;
      const newPayload = payload.new && typeof payload.new === "object" ? (payload.new as Record<string, unknown>) : payload;
      const oldTransform = oldPayload.transform && typeof oldPayload.transform === "object" ? (oldPayload.transform as Record<string, unknown>) : null;
      const newTransform = newPayload.transform && typeof newPayload.transform === "object" ? (newPayload.transform as Record<string, unknown>) : null;
      const oldPos = Array.isArray(oldTransform?.position) ? (oldTransform?.position as unknown[]) : null;
      const newPos = Array.isArray(newTransform?.position) ? (newTransform?.position as unknown[]) : null;
      const oldX = oldPos ? Number(oldPos[0]) : findNum(oldPayload, ["old_x", "x", "from_x"]);
      const oldY = oldPos ? Number(oldPos[1]) : findNum(oldPayload, ["old_y", "y", "from_y"]);
      const newX = newPos ? Number(newPos[0]) : findNum(newPayload, ["new_x", "x", "to_x"]);
      const newY = newPos ? Number(newPos[1]) : findNum(newPayload, ["new_y", "y", "to_y"]);
      if (Number.isFinite(oldX) && Number.isFinite(oldY) && Number.isFinite(newX) && Number.isFinite(newY)) {
        moves.push({ id, oldX, oldY, newX, newY });
      }
    }
  }
  if (adds.length === 0 && removes.length === 0 && moves.length === 0) {
    return null;
  }
  return { adds, removes, moves };
}

export function useAgentState({ hasTauri }: UseAgentStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    agentConversation: [],
    agentLoading: false,
    agentError: "",
    agentDiffPreview: null,
    agentDiffApproved: false,
  });

  const patch = (p: Partial<AgentState>): void => dispatch({ type: "patch", patch: p });

  const executeAgentTurn = async (args: ExecuteTurnArgs): Promise<ExecuteTurnResult | null> => {
    if (!hasTauri) {
      patch({ agentError: "Agent runtime requires Tauri runtime." });
      return null;
    }
    if (!args.projectPath.trim()) {
      patch({ agentError: "Project path is required for agent runtime." });
      return null;
    }
    if (!args.intent.trim()) {
      patch({ agentError: "Agent intent is empty." });
      return null;
    }
    let approvalsObj: Record<string, unknown> = {};
    if (args.approvalsJson.trim()) {
      try {
        const parsed = JSON.parse(args.approvalsJson) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          approvalsObj = parsed as Record<string, unknown>;
        } else {
          patch({ agentError: "Approvals JSON must be an object." });
          return null;
        }
      } catch (err) {
        patch({ agentError: err instanceof Error ? `Invalid approvals JSON: ${err.message}` : "Invalid approvals JSON." });
        return null;
      }
    }
    approvalsObj.apply_diff = args.applyDiff;
    approvalsObj.run_job = args.runJob;
    const selectedIdx = Number(args.selectedOptionIndex);
    if (Number.isFinite(selectedIdx) && selectedIdx >= 0) {
      approvalsObj.selected_option_index = Math.round(selectedIdx);
    }
    const approvalsJson = JSON.stringify(approvalsObj);
    const userMessage: AgentConversationMessage = {
      role: "user",
      content: args.intent.trim(),
      timestamp: Date.now(),
    };
    const outboundConversation = [...state.agentConversation, userMessage];
    patch({
      agentLoading: true,
      agentError: "",
      agentConversation: outboundConversation,
      agentDiffPreview: null,
      agentDiffApproved: false,
    });
    try {
      const payload = await tauriInvoke<{ response: Record<string, unknown>; summary?: string }>("execute_agent_turn", {
        projectPath: args.projectPath,
        intent: args.intent,
        conversationJson: JSON.stringify(outboundConversation),
        approvalsJson,
      });
      const assistantActions = ((payload.response.actions as unknown[]) ?? [])
        .filter((v): v is Record<string, unknown> => !!v && typeof v === "object")
        .map((v) => ({
          kind: String(v.kind ?? "action"),
          payload: v.payload && typeof v.payload === "object" ? (v.payload as Record<string, unknown>) : null,
        }));
      const assistantMessage: AgentConversationMessage = {
        role: "assistant",
        content: String(payload.summary || payload.response.plan || "Completed."),
        timestamp: Date.now(),
        actions: assistantActions,
        warnings: ((payload.response.warnings as unknown[]) ?? []).map((v) => String(v)),
        errors: ((payload.response.errors as unknown[]) ?? []).map((v) => String(v)),
      };
      patch({
        agentLoading: false,
        agentConversation: [...outboundConversation, assistantMessage],
        agentDiffPreview: parseAgentDiffPreview(payload.response),
        agentDiffApproved: args.applyDiff,
      });
      return {
        response: payload.response,
        approvalsJson,
        assistantMessage,
      };
    } catch (err) {
      patch({ agentLoading: false, agentError: err instanceof Error ? err.message : String(err) });
      return null;
    }
  };

  const clearConversation = (): void => {
    patch({ agentConversation: [], agentDiffPreview: null, agentDiffApproved: false, agentError: "" });
  };

  return {
    state,
    patch,
    executeAgentTurn,
    clearConversation,
  };
}
