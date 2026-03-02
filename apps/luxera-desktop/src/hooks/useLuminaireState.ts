import { useReducer } from "react";
import type { GeometryOperationResult, PhotometryVerifyResponse, ToolOperationResult } from "../types";
import { tauriDialogOpen, tauriInvoke } from "../utils/tauri";

export interface LuminaireState {
  photometryFilePath: string;
  photometryAssetId: string;
  photometryFormat: string;
  photometryLibraryQuery: string;
  selectedPhotometryAssetId: string;
  photometryVerifyLoading: boolean;
  photometryVerifyError: string;
  photometryVerifyResult: Record<string, unknown> | null;
  polarPlotData: Record<string, unknown> | null;
  polarPlotLoading: boolean;
  polarPlotError: string;
  luminaireAssetId: string;
  luminaireId: string;
  luminaireName: string;
  luminaireX: string;
  luminaireY: string;
  luminaireZ: string;
  luminaireYaw: string;
  luminairePitch: string;
  luminaireRoll: string;
  luminaireMaintenance: string;
  luminaireMultiplier: string;
  luminaireTilt: string;
  luminaireLoading: boolean;
  luminaireLogStdout: string;
  luminaireLogStderr: string;
  luminaireError: string;
  arrayRoomId: string;
  arrayAssetId: string;
  arrayRows: string;
  arrayCols: string;
  arrayMarginM: string;
  arrayMountHeightM: string;
  aimLuminaireId: string;
  aimYawDeg: string;
  batchYawDeg: string;
  batchMaintenanceFactor: string;
  batchFluxMultiplier: string;
  batchTiltDeg: string;
}

type Action = { type: "patch"; patch: Partial<LuminaireState> };

function reducer(state: LuminaireState, action: Action): LuminaireState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    default:
      return state;
  }
}

interface UseLuminaireStateArgs {
  hasTauri: boolean;
  projectPath: string;
  onProjectMutated: () => Promise<void>;
}

export function useLuminaireState({ hasTauri, projectPath, onProjectMutated }: UseLuminaireStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    photometryFilePath: "",
    photometryAssetId: "",
    photometryFormat: "",
    photometryLibraryQuery: "",
    selectedPhotometryAssetId: "",
    photometryVerifyLoading: false,
    photometryVerifyError: "",
    photometryVerifyResult: null,
    polarPlotData: null,
    polarPlotLoading: false,
    polarPlotError: "",
    luminaireAssetId: "",
    luminaireId: "",
    luminaireName: "",
    luminaireX: "0",
    luminaireY: "0",
    luminaireZ: "3",
    luminaireYaw: "0",
    luminairePitch: "0",
    luminaireRoll: "0",
    luminaireMaintenance: "1",
    luminaireMultiplier: "1",
    luminaireTilt: "0",
    luminaireLoading: false,
    luminaireLogStdout: "",
    luminaireLogStderr: "",
    luminaireError: "",
    arrayRoomId: "",
    arrayAssetId: "",
    arrayRows: "2",
    arrayCols: "3",
    arrayMarginM: "0.5",
    arrayMountHeightM: "2.8",
    aimLuminaireId: "",
    aimYawDeg: "0",
    batchYawDeg: "",
    batchMaintenanceFactor: "",
    batchFluxMultiplier: "",
    batchTiltDeg: "",
  });

  const patch = (p: Partial<LuminaireState>): void => dispatch({ type: "patch", patch: p });

  const browsePhotometryPath = async (defaultPath?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Photometry browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Import Photometry",
        defaultPath: (defaultPath ?? state.photometryFilePath).trim() || undefined,
        multiple: false,
        directory: false,
        filters: [
          { name: "Photometry", extensions: ["ies", "ldt"] },
          { name: "All Files", extensions: ["*"] },
        ],
      });
      if (typeof picked === "string" && picked.trim()) {
        patch({ photometryFilePath: picked, luminaireError: "" });
      }
    } catch (err) {
      patch({ luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applyLuminaireResult = async (res: GeometryOperationResult): Promise<void> => {
    patch({
      luminaireLoading: false,
      luminaireLogStdout: res.stdout,
      luminaireLogStderr: res.stderr,
      luminaireError: res.success ? "" : `Luminaire operation failed (exit ${res.exitCode}).`,
    });
    if (res.success && res.project) {
      await onProjectMutated();
    }
  };

  const addPhotometryAsset = async (
    inputs?: Partial<Pick<LuminaireState, "photometryFilePath" | "photometryAssetId" | "photometryFormat">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Luminaire authoring requires Tauri runtime." });
      return;
    }
    const filePath = (inputs?.photometryFilePath ?? state.photometryFilePath).trim();
    const assetId = (inputs?.photometryAssetId ?? state.photometryAssetId).trim();
    const format = (inputs?.photometryFormat ?? state.photometryFormat).trim();
    if (!filePath) {
      patch({ luminaireError: "Photometry file path is required." });
      return;
    }
    patch({ luminaireLoading: true, luminaireError: "", luminaireLogStdout: "", luminaireLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_photometry_to_project", {
        projectPath,
        filePath,
        assetId: assetId || null,
        format: format || null,
      });
      await applyLuminaireResult(res);
    } catch (err) {
      patch({ luminaireLoading: false, luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const verifyImportPhotometry = async (
    inputs?: Partial<Pick<LuminaireState, "photometryFilePath" | "photometryFormat">>,
  ): Promise<void> => {
    const path = (inputs?.photometryFilePath ?? state.photometryFilePath).trim();
    const format = (inputs?.photometryFormat ?? state.photometryFormat).trim();
    if (!path) {
      patch({ photometryVerifyError: "Photometry file path is required.", photometryVerifyResult: null });
      return;
    }
    patch({ photometryVerifyLoading: true, photometryVerifyError: "", photometryVerifyResult: null });
    try {
      const res = await tauriInvoke<PhotometryVerifyResponse>("verify_photometry_file_input", {
        filePath: path,
        format: format || null,
      });
      patch({
        photometryVerifyLoading: false,
        photometryVerifyError: res.ok ? "" : String(res.error ?? "Photometry verification failed."),
        photometryVerifyResult: res.result ?? null,
      });
    } catch (err) {
      patch({
        photometryVerifyLoading: false,
        photometryVerifyError: err instanceof Error ? err.message : String(err),
        photometryVerifyResult: null,
      });
    }
  };

  const verifySelectedProjectPhotometry = async (assetId: string): Promise<void> => {
    if (!assetId.trim()) {
      patch({ photometryVerifyError: "Select a project photometry asset.", photometryVerifyResult: null });
      return;
    }
    patch({ photometryVerifyLoading: true, photometryVerifyError: "", photometryVerifyResult: null });
    try {
      const res = await tauriInvoke<PhotometryVerifyResponse>("verify_project_photometry_asset", {
        projectPath,
        assetId,
      });
      patch({
        photometryVerifyLoading: false,
        photometryVerifyError: res.ok ? "" : String(res.error ?? "Photometry verification failed."),
        photometryVerifyResult: res.result ?? null,
      });
    } catch (err) {
      patch({
        photometryVerifyLoading: false,
        photometryVerifyError: err instanceof Error ? err.message : String(err),
        photometryVerifyResult: null,
      });
    }
  };

  const loadPolarDistribution = async (filePath: string, format?: string | null): Promise<void> => {
    if (!hasTauri) {
      patch({ polarPlotError: "Polar distribution requires Tauri runtime.", polarPlotData: null });
      return;
    }
    if (!filePath.trim()) {
      patch({ polarPlotError: "Selected photometry asset has no file path.", polarPlotData: null });
      return;
    }
    patch({ polarPlotLoading: true, polarPlotError: "", polarPlotData: null });
    try {
      const payload = await tauriInvoke<Record<string, unknown>>("get_photometry_polar_data", {
        filePath,
        format: format && format.trim() ? format.trim() : null,
      });
      patch({ polarPlotLoading: false, polarPlotData: payload, polarPlotError: "" });
    } catch (err) {
      patch({
        polarPlotLoading: false,
        polarPlotData: null,
        polarPlotError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const addLuminaire = async (
    inputs?: Partial<
      Pick<
        LuminaireState,
        | "luminaireAssetId"
        | "luminaireId"
        | "luminaireName"
        | "luminaireX"
        | "luminaireY"
        | "luminaireZ"
        | "luminaireYaw"
        | "luminairePitch"
        | "luminaireRoll"
        | "luminaireMaintenance"
        | "luminaireMultiplier"
        | "luminaireTilt"
      >
    >,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Luminaire authoring requires Tauri runtime." });
      return;
    }
    const assetIdRaw = inputs?.luminaireAssetId ?? state.luminaireAssetId;
    const luminaireIdRaw = inputs?.luminaireId ?? state.luminaireId;
    const luminaireNameRaw = inputs?.luminaireName ?? state.luminaireName;
    if (!assetIdRaw.trim()) {
      patch({ luminaireError: "Luminaire asset id is required." });
      return;
    }
    const x = Number(inputs?.luminaireX ?? state.luminaireX);
    const y = Number(inputs?.luminaireY ?? state.luminaireY);
    const z = Number(inputs?.luminaireZ ?? state.luminaireZ);
    const yaw = Number(inputs?.luminaireYaw ?? state.luminaireYaw);
    const pitch = Number(inputs?.luminairePitch ?? state.luminairePitch);
    const roll = Number(inputs?.luminaireRoll ?? state.luminaireRoll);
    const maintenance = Number(inputs?.luminaireMaintenance ?? state.luminaireMaintenance);
    const multiplier = Number(inputs?.luminaireMultiplier ?? state.luminaireMultiplier);
    const tilt = Number(inputs?.luminaireTilt ?? state.luminaireTilt);
    if (![x, y, z, yaw, pitch, roll, maintenance, multiplier, tilt].every(Number.isFinite)) {
      patch({ luminaireError: "Luminaire numeric fields are invalid." });
      return;
    }
    patch({ luminaireLoading: true, luminaireError: "", luminaireLogStdout: "", luminaireLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_luminaire_to_project", {
        projectPath,
        assetId: assetIdRaw.trim(),
        luminaireId: luminaireIdRaw.trim() ? luminaireIdRaw.trim() : null,
        name: luminaireNameRaw.trim() ? luminaireNameRaw.trim() : null,
        x,
        y,
        z,
        yaw,
        pitch,
        roll,
        maintenance,
        multiplier,
        tilt,
      });
      await applyLuminaireResult(res);
    } catch (err) {
      patch({ luminaireLoading: false, luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const arrayLuminaires = async (): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Luminaire arrays require Tauri runtime." });
      return;
    }
    if (!state.arrayRoomId.trim() || !state.arrayAssetId.trim()) {
      patch({ luminaireError: "Array room id and asset id are required." });
      return;
    }
    const rows = Number(state.arrayRows);
    const cols = Number(state.arrayCols);
    const marginM = Number(state.arrayMarginM);
    const mountHeightM = Number(state.arrayMountHeightM);
    if (![rows, cols, marginM, mountHeightM].every(Number.isFinite) || rows < 1 || cols < 1) {
      patch({ luminaireError: "Luminaire array inputs are invalid." });
      return;
    }
    patch({ luminaireLoading: true, luminaireError: "", luminaireLogStdout: "", luminaireLogStderr: "" });
    try {
      const res = await tauriInvoke<ToolOperationResult>("array_luminaires_in_project", {
        projectPath,
        roomId: state.arrayRoomId.trim(),
        assetId: state.arrayAssetId.trim(),
        rows: Math.round(rows),
        cols: Math.round(cols),
        marginM,
        mountHeightM,
      });
      patch({
        luminaireLoading: false,
        luminaireError: res.success ? "" : (res.message || "Luminaire array operation failed."),
      });
      if (res.success && res.project) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ luminaireLoading: false, luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const aimLuminaire = async (): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Luminaire aiming requires Tauri runtime." });
      return;
    }
    if (!state.aimLuminaireId.trim()) {
      patch({ luminaireError: "Luminaire id is required for aiming." });
      return;
    }
    const yawDeg = Number(state.aimYawDeg);
    if (!Number.isFinite(yawDeg)) {
      patch({ luminaireError: "Yaw degrees is invalid." });
      return;
    }
    patch({ luminaireLoading: true, luminaireError: "" });
    try {
      const res = await tauriInvoke<ToolOperationResult>("aim_luminaire_in_project", {
        projectPath,
        luminaireId: state.aimLuminaireId.trim(),
        yawDeg,
      });
      patch({
        luminaireLoading: false,
        luminaireError: res.success ? "" : (res.message || "Luminaire aim failed."),
      });
      if (res.success && res.project) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ luminaireLoading: false, luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const batchUpdateLuminaires = async (luminaireIdsCsv: string): Promise<void> => {
    if (!hasTauri) {
      patch({ luminaireError: "Batch luminaire operations require Tauri runtime." });
      return;
    }
    const idsCsv = luminaireIdsCsv.trim();
    if (!idsCsv) {
      patch({ luminaireError: "No luminaires selected for batch update." });
      return;
    }
    const parseMaybe = (value: string): number | null => {
      if (!value.trim()) {
        return null;
      }
      const n = Number(value);
      return Number.isFinite(n) ? n : Number.NaN;
    };
    const yaw = parseMaybe(state.batchYawDeg);
    const maintenance = parseMaybe(state.batchMaintenanceFactor);
    const flux = parseMaybe(state.batchFluxMultiplier);
    const tilt = parseMaybe(state.batchTiltDeg);
    if ([yaw, maintenance, flux, tilt].some((v) => typeof v === "number" && Number.isNaN(v))) {
      patch({ luminaireError: "Batch luminaire numeric values are invalid." });
      return;
    }
    if (yaw === null && maintenance === null && flux === null && tilt === null) {
      patch({ luminaireError: "Provide at least one batch luminaire field to update." });
      return;
    }
    patch({ luminaireLoading: true, luminaireError: "" });
    try {
      const res = await tauriInvoke<ToolOperationResult>("batch_update_luminaires_in_project", {
        projectPath,
        luminaireIdsCsv: idsCsv,
        yawDeg: yaw,
        maintenanceFactor: maintenance,
        fluxMultiplier: flux,
        tiltDeg: tilt,
      });
      patch({
        luminaireLoading: false,
        luminaireError: res.success ? "" : (res.message || "Batch update failed."),
      });
      if (res.success && res.project) {
        await onProjectMutated();
      }
    } catch (err) {
      patch({ luminaireLoading: false, luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  return {
    state,
    patch,
    browsePhotometryPath,
    addPhotometryAsset,
    verifyImportPhotometry,
    verifySelectedProjectPhotometry,
    loadPolarDistribution,
    addLuminaire,
    arrayLuminaires,
    aimLuminaire,
    batchUpdateLuminaires,
  };
}
