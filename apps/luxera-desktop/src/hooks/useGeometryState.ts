import { useReducer } from "react";
import type { GeometryOperationResult } from "../types";
import { tauriDialogOpen, tauriInvoke } from "../utils/tauri";

export interface GeometryState {
  geomRoomName: string;
  geomRoomWidth: string;
  geomRoomLength: string;
  geomRoomHeight: string;
  geomOriginX: string;
  geomOriginY: string;
  geomOriginZ: string;
  geomImportPath: string;
  geomImportFormat: string;
  geomCleanSnapTolerance: string;
  geomCleanDetectRooms: boolean;
  geomCleanMergeCoplanar: boolean;
  geomLoading: boolean;
  geomLogStdout: string;
  geomLogStderr: string;
  geomError: string;
  editRoomId: string;
  arrayRoomId: string;
}

type GeometryAction = { type: "patch"; patch: Partial<GeometryState> };

function reducer(state: GeometryState, action: GeometryAction): GeometryState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    default:
      return state;
  }
}

interface UseGeometryStateArgs {
  hasTauri: boolean;
  projectPath: string;
  onProjectMutated: () => Promise<void>;
}

export function useGeometryState({ hasTauri, projectPath, onProjectMutated }: UseGeometryStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    geomRoomName: "",
    geomRoomWidth: "4",
    geomRoomLength: "4",
    geomRoomHeight: "3",
    geomOriginX: "0",
    geomOriginY: "0",
    geomOriginZ: "0",
    geomImportPath: "",
    geomImportFormat: "",
    geomCleanSnapTolerance: "0.001",
    geomCleanDetectRooms: true,
    geomCleanMergeCoplanar: true,
    geomLoading: false,
    geomLogStdout: "",
    geomLogStderr: "",
    geomError: "",
    editRoomId: "",
    arrayRoomId: "",
  });

  const patch = (patchState: Partial<GeometryState>): void => {
    dispatch({ type: "patch", patch: patchState });
  };

  const browseGeometryImportPath = async (defaultPath?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ geomError: "Geometry browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Import Geometry",
        defaultPath: (defaultPath ?? state.geomImportPath).trim() || undefined,
        multiple: false,
        directory: false,
        filters: [
          { name: "Geometry Files", extensions: ["dxf", "obj", "gltf", "glb", "fbx", "skp", "ifc", "dwg"] },
          { name: "All Files", extensions: ["*"] },
        ],
      });
      if (typeof picked === "string" && picked.trim()) {
        patch({ geomImportPath: picked, geomError: "" });
      }
    } catch (err) {
      patch({ geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  const addRoom = async (inputs?: Partial<Pick<GeometryState, "geomRoomName" | "geomRoomWidth" | "geomRoomLength" | "geomRoomHeight" | "geomOriginX" | "geomOriginY" | "geomOriginZ">>): Promise<void> => {
    if (!hasTauri) {
      patch({ geomError: "Geometry authoring requires Tauri runtime." });
      return;
    }
    const roomName = inputs?.geomRoomName ?? state.geomRoomName;
    const width = Number(inputs?.geomRoomWidth ?? state.geomRoomWidth);
    const length = Number(inputs?.geomRoomLength ?? state.geomRoomLength);
    const height = Number(inputs?.geomRoomHeight ?? state.geomRoomHeight);
    const originX = Number(inputs?.geomOriginX ?? state.geomOriginX);
    const originY = Number(inputs?.geomOriginY ?? state.geomOriginY);
    const originZ = Number(inputs?.geomOriginZ ?? state.geomOriginZ);
    if (![width, length, height, originX, originY, originZ].every(Number.isFinite)) {
      patch({ geomError: "Room dimensions/origin are invalid." });
      return;
    }
    patch({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_room_to_project", {
        projectPath,
        name: roomName.trim() || null,
        width,
        length,
        height,
        originX,
        originY,
        originZ,
      });
      patch({
        geomLoading: false,
        geomLogStdout: res.stdout,
        geomLogStderr: res.stderr,
        geomError: res.success ? "" : (res.stderr || "Room creation failed."),
      });
      if (res.success) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ geomLoading: false, geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  const editRoom = async (): Promise<void> => {
    if (!hasTauri) {
      patch({ geomError: "Geometry authoring requires Tauri runtime." });
      return;
    }
    if (!state.editRoomId.trim()) {
      patch({ geomError: "Room id is required for edit." });
      return;
    }
    const width = Number(state.geomRoomWidth);
    const length = Number(state.geomRoomLength);
    const height = Number(state.geomRoomHeight);
    const originX = Number(state.geomOriginX);
    const originY = Number(state.geomOriginY);
    const originZ = Number(state.geomOriginZ);
    if (![width, length, height, originX, originY, originZ].every(Number.isFinite)) {
      patch({ geomError: "Room dimensions/origin are invalid." });
      return;
    }
    patch({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("edit_room_in_project", {
        projectPath,
        roomId: state.editRoomId.trim(),
        name: state.geomRoomName.trim() || null,
        width,
        length,
        height,
        originX,
        originY,
        originZ,
      });
      patch({
        geomLoading: false,
        geomLogStdout: res.stdout,
        geomLogStderr: res.stderr,
        geomError: res.success ? "" : (res.stderr || "Room edit failed."),
      });
      if (res.success) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ geomLoading: false, geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  const importGeometry = async (inputs?: Partial<Pick<GeometryState, "geomImportPath" | "geomImportFormat">>): Promise<void> => {
    if (!hasTauri) {
      patch({ geomError: "Geometry import requires Tauri runtime." });
      return;
    }
    const importPath = (inputs?.geomImportPath ?? state.geomImportPath).trim();
    const importFormat = (inputs?.geomImportFormat ?? state.geomImportFormat).trim();
    if (!importPath) {
      patch({ geomError: "Geometry file path is required." });
      return;
    }
    patch({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("import_geometry_to_project", {
        projectPath,
        filePath: importPath,
        format: importFormat || null,
      });
      patch({
        geomLoading: false,
        geomLogStdout: res.stdout,
        geomLogStderr: res.stderr,
        geomError: res.success ? "" : (res.stderr || "Geometry import failed."),
      });
      if (res.success) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ geomLoading: false, geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  const cleanGeometry = async (
    inputs?: Partial<Pick<GeometryState, "geomCleanSnapTolerance" | "geomCleanMergeCoplanar" | "geomCleanDetectRooms">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ geomError: "Geometry clean requires Tauri runtime." });
      return;
    }
    const snapTolerance = Number(inputs?.geomCleanSnapTolerance ?? state.geomCleanSnapTolerance);
    if (!Number.isFinite(snapTolerance) || snapTolerance <= 0) {
      patch({ geomError: "Snap tolerance must be positive." });
      return;
    }
    patch({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("clean_geometry_in_project", {
        projectPath,
        snapTolerance,
        mergeCoplanar: inputs?.geomCleanMergeCoplanar ?? state.geomCleanMergeCoplanar,
        detectRooms: inputs?.geomCleanDetectRooms ?? state.geomCleanDetectRooms,
      });
      patch({
        geomLoading: false,
        geomLogStdout: res.stdout,
        geomLogStderr: res.stderr,
        geomError: res.success ? "" : (res.stderr || "Geometry clean failed."),
      });
      if (res.success) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ geomLoading: false, geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  return {
    state,
    patch,
    setEditRoomId: (editRoomId: string) => patch({ editRoomId }),
    setArrayRoomId: (arrayRoomId: string) => patch({ arrayRoomId }),
    browseGeometryImportPath,
    addRoom,
    editRoom,
    importGeometry,
    cleanGeometry,
  };
}
