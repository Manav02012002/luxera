import { useReducer } from "react";
import type { GeometryOperationResult } from "../types";
import { tauriInvoke } from "../utils/tauri";

export interface CalcSetupState {
  gridName: string;
  gridWidth: string;
  gridHeight: string;
  gridElevation: string;
  gridNx: string;
  gridNy: string;
  gridOriginX: string;
  gridOriginY: string;
  gridOriginZ: string;
  gridRoomId: string;
  jobIdInput: string;
  jobTypeInput: string;
  jobBackendInput: string;
  jobSeedInput: string;
  workplanePreset: "floor" | "desk" | "standing" | "custom";
  calcSetupLoading: boolean;
  calcSetupLogStdout: string;
  calcSetupLogStderr: string;
  calcSetupError: string;
}

type Action = { type: "patch"; patch: Partial<CalcSetupState> };

function reducer(state: CalcSetupState, action: Action): CalcSetupState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    default:
      return state;
  }
}

interface UseCalcSetupStateArgs {
  hasTauri: boolean;
  projectPath: string;
  onProjectMutated: () => Promise<void>;
}

export function useCalcSetupState({ hasTauri, projectPath, onProjectMutated }: UseCalcSetupStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    gridName: "",
    gridWidth: "4",
    gridHeight: "4",
    gridElevation: "0.8",
    gridNx: "9",
    gridNy: "9",
    gridOriginX: "0",
    gridOriginY: "0",
    gridOriginZ: "0",
    gridRoomId: "",
    jobIdInput: "",
    jobTypeInput: "direct",
    jobBackendInput: "cpu",
    jobSeedInput: "0",
    workplanePreset: "custom",
    calcSetupLoading: false,
    calcSetupLogStdout: "",
    calcSetupLogStderr: "",
    calcSetupError: "",
  });

  const patch = (p: Partial<CalcSetupState>): void => dispatch({ type: "patch", patch: p });

  const applyCalcSetupResult = async (res: GeometryOperationResult): Promise<void> => {
    patch({
      calcSetupLoading: false,
      calcSetupLogStdout: res.stdout,
      calcSetupLogStderr: res.stderr,
      calcSetupError: res.success ? "" : `Calculation setup operation failed (exit ${res.exitCode}).`,
    });
    if (res.success && res.project) {
      await onProjectMutated();
    }
  };

  const addGrid = async (
    inputs?: Partial<
      Pick<
        CalcSetupState,
        "gridName" | "gridWidth" | "gridHeight" | "gridElevation" | "gridNx" | "gridNy" | "gridOriginX" | "gridOriginY" | "gridOriginZ" | "gridRoomId"
      >
    >,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ calcSetupError: "Calculation setup requires Tauri runtime." });
      return;
    }
    const gridName = inputs?.gridName ?? state.gridName;
    const gridRoomId = inputs?.gridRoomId ?? state.gridRoomId;
    const width = Number(inputs?.gridWidth ?? state.gridWidth);
    const height = Number(inputs?.gridHeight ?? state.gridHeight);
    const elevation = Number(inputs?.gridElevation ?? state.gridElevation);
    const nx = Number(inputs?.gridNx ?? state.gridNx);
    const ny = Number(inputs?.gridNy ?? state.gridNy);
    const ox = Number(inputs?.gridOriginX ?? state.gridOriginX);
    const oy = Number(inputs?.gridOriginY ?? state.gridOriginY);
    const oz = Number(inputs?.gridOriginZ ?? state.gridOriginZ);
    if (![width, height, elevation, nx, ny, ox, oy, oz].every(Number.isFinite) || width <= 0 || height <= 0 || nx < 2 || ny < 2) {
      patch({ calcSetupError: "Grid inputs are invalid." });
      return;
    }
    patch({ calcSetupLoading: true, calcSetupError: "", calcSetupLogStdout: "", calcSetupLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_grid_to_project", {
        projectPath,
        name: gridName.trim() ? gridName.trim() : null,
        width,
        height,
        elevation,
        nx: Math.round(nx),
        ny: Math.round(ny),
        originX: ox,
        originY: oy,
        originZ: oz,
        roomId: gridRoomId.trim() ? gridRoomId.trim() : null,
      });
      await applyCalcSetupResult(res);
    } catch (err) {
      patch({ calcSetupLoading: false, calcSetupError: err instanceof Error ? err.message : String(err) });
    }
  };

  const addJob = async (
    inputs?: Partial<Pick<CalcSetupState, "jobIdInput" | "jobTypeInput" | "jobBackendInput" | "jobSeedInput">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ calcSetupError: "Calculation setup requires Tauri runtime." });
      return;
    }
    const jobIdInput = inputs?.jobIdInput ?? state.jobIdInput;
    const jobTypeInput = inputs?.jobTypeInput ?? state.jobTypeInput;
    const jobBackendInput = inputs?.jobBackendInput ?? state.jobBackendInput;
    const jobSeedInput = inputs?.jobSeedInput ?? state.jobSeedInput;
    if (!jobTypeInput.trim()) {
      patch({ calcSetupError: "Job type is required." });
      return;
    }
    const seed = Number(jobSeedInput);
    if (!Number.isFinite(seed)) {
      patch({ calcSetupError: "Job seed is invalid." });
      return;
    }
    patch({ calcSetupLoading: true, calcSetupError: "", calcSetupLogStdout: "", calcSetupLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_job_to_project", {
        projectPath,
        jobId: jobIdInput.trim() ? jobIdInput.trim() : null,
        jobType: jobTypeInput.trim(),
        backend: jobBackendInput.trim() ? jobBackendInput.trim() : "cpu",
        seed: Math.round(seed),
      });
      await applyCalcSetupResult(res);
    } catch (err) {
      patch({ calcSetupLoading: false, calcSetupError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applyWorkplanePreset = (value: "floor" | "desk" | "standing" | "custom"): void => {
    patch({ workplanePreset: value });
    if (value === "floor") {
      patch({ gridElevation: "0.0" });
    } else if (value === "desk") {
      patch({ gridElevation: "0.75" });
    } else if (value === "standing") {
      patch({ gridElevation: "1.2" });
    }
  };

  return {
    state,
    patch,
    addGrid,
    addJob,
    applyWorkplanePreset,
  };
}
