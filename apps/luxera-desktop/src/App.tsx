import { useEffect, useMemo, useReducer } from "react";
import {
  AppShell,
  ConsolePanel,
  InspectorPanel,
  MetricCard,
  Sidebar,
  SidebarSection,
  ToolbarButton,
} from "@luxera/luxera-ui";
import { DataTable } from "./components/DataTable";
import { useArtifacts } from "./hooks/useArtifacts";
import { useJobRunner } from "./hooks/useJobRunner";
import { buildDesktopViewModel, type DesktopResultBundle } from "./resultContracts";
import type {
  AppState,
  BackendContract,
  ExportOperationResult,
  GeometryOperationResult,
  JsonRow,
  ProjectDocument,
  ProjectJobsResponse,
  ProjectValidationResult,
  RecentRun,
} from "./types";
import { flattenJsonRows, firstNumeric, objectToRows, rowsToPoints } from "./utils/table";
import { hasTauriRuntime, tauriInvoke } from "./utils/tauri";

const projectItems = ["Project", "Geometry", "Luminaires", "Calculation", "Reports"];

function fmt(value: number | undefined, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "N/A";
}

function fmtUnix(ts: number | undefined): string {
  if (typeof ts !== "number" || !Number.isFinite(ts) || ts <= 0) {
    return "N/A";
  }
  return new Date(ts * 1000).toLocaleString();
}

const initialState: AppState = {
  resultDir: "",
  loading: false,
  error: "",
  bundle: null,
  model: null,
  recentRuns: [],
  recentLoading: false,
  contract: null,
  projectPath: "",
  projectName: "",
  projectJobs: [],
  jobsLoading: false,
  selectedJobId: "",
  projectDoc: null,
  projectDocContent: "",
  projectDocDirty: false,
  projectValidation: null,
  projectLifecycleLoading: false,
  projectLifecycleError: "",
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
  photometryFilePath: "",
  photometryAssetId: "",
  photometryFormat: "",
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
  calcSetupLoading: false,
  calcSetupLogStdout: "",
  calcSetupLogStderr: "",
  calcSetupError: "",
  exportJobId: "",
  exportOutputPath: "out/export_artifact",
  exportLoading: false,
  exportLogStdout: "",
  exportLogStderr: "",
  exportError: "",
  agentIntent: "",
  agentApprovalsJson: "{}",
  agentLoading: false,
  agentError: "",
  agentResponse: null,
  selectedTableTitle: "",
  selectedRowIndex: -1,
  selectedRow: null,
};

function appReducer(state: AppState, patch: Partial<AppState>): AppState {
  return { ...state, ...patch };
}

export default function App() {
  const [state, patchState] = useReducer(appReducer, initialState);
  const hasTauri = hasTauriRuntime();
  const artifacts = useArtifacts({ hasTauri });

  const model = state.model;
  const rawResultRows = useMemo(() => flattenJsonRows(model?.raw.result ?? null, "result"), [model?.raw.result]);
  const rawTablesRows = useMemo(() => flattenJsonRows(model?.raw.tables ?? null, "tables"), [model?.raw.tables]);
  const rawResultsRows = useMemo(() => flattenJsonRows(model?.raw.results ?? null, "results"), [model?.raw.results]);
  const rawRoadSummaryRows = useMemo(() => flattenJsonRows(model?.raw.roadSummary ?? null, "roadSummary"), [model?.raw.roadSummary]);
  const rawRoadwaySubmissionRows = useMemo(
    () => flattenJsonRows(model?.raw.roadwaySubmission ?? null, "roadwaySubmission"),
    [model?.raw.roadwaySubmission],
  );
  const agentResponseRows = useMemo(() => flattenJsonRows(state.agentResponse ?? null, "agent"), [state.agentResponse]);
  const selectedPoint = useMemo(() => {
    const row = state.selectedRow;
    const x = firstNumeric(row, ["x", "observer_x", "point_x"]);
    const y = firstNumeric(row, ["y", "observer_y", "point_y", "lane_number"]);
    const z = firstNumeric(row, ["z", "observer_z", "point_z", "elevation"]);
    if (x === undefined || y === undefined) {
      return null;
    }
    return { x, y, z };
  }, [state.selectedRow]);
  const selectableRowsByTitle = useMemo<Record<string, JsonRow[]>>(
    () => ({
      Grids: (model?.tables.grids ?? []) as JsonRow[],
      "Vertical Planes": (model?.tables.verticalPlanes ?? []) as JsonRow[],
      "Point Sets": (model?.tables.pointSets ?? []) as JsonRow[],
      "Roadway Lane Metrics": (model?.roadway.laneMetrics ?? []) as JsonRow[],
      "Roadway Observer Luminance Views": (model?.roadway.observerLuminanceViews ?? []) as JsonRow[],
      "Roadway Observer Glare Views": (model?.roadway.observerGlareViews ?? []) as JsonRow[],
      "UGR Views": (model?.ugr.views ?? []) as JsonRow[],
    }),
    [model],
  );
  const viewportPoints = useMemo(
    () => rowsToPoints(selectableRowsByTitle[state.selectedTableTitle] ?? []),
    [state.selectedTableTitle, selectableRowsByTitle],
  );
  const viewportBounds = useMemo(() => {
    if (viewportPoints.length === 0) {
      return null;
    }
    let minX = viewportPoints[0].x;
    let minY = viewportPoints[0].y;
    let maxX = viewportPoints[0].x;
    let maxY = viewportPoints[0].y;
    for (const p of viewportPoints) {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
    return { minX, minY, maxX, maxY };
  }, [viewportPoints]);
  const selectRow = (title: string, row: JsonRow, index: number): void => {
    patchState({ selectedTableTitle: title, selectedRow: row, selectedRowIndex: index });
  };

  const refreshRecentRuns = async (): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    patchState({ recentLoading: true });
    try {
      const runs = await tauriInvoke<RecentRun[]>("list_recent_runs", { limit: 20 });
      patchState({ recentRuns: runs, recentLoading: false });
    } catch {
      patchState({ recentLoading: false });
    }
  };

  const loadContract = async (): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    try {
      const contract = await tauriInvoke<BackendContract>("desktop_backend_contract", {});
      patchState({ contract });
    } catch {
      // Best effort only.
    }
  };

  const loadOutputs = async (explicitDir?: string): Promise<void> => {
    if (!hasTauri) {
      patchState({ error: "Backend loading requires Tauri runtime (use `pnpm --filter luxera-desktop tauri:dev`)." });
      return;
    }
    patchState({ loading: true, error: "" });
    try {
      const payload = await tauriInvoke<DesktopResultBundle>("load_backend_outputs", {
        resultDir: explicitDir?.trim() ? explicitDir.trim() : null,
      });
      const nextModel = buildDesktopViewModel(payload);
      patchState({
        bundle: payload,
        model: nextModel,
        resultDir: payload.sourceDir,
        loading: false,
      });
      artifacts.primeArtifactPath(`${payload.sourceDir}/result.json`);
      await artifacts.loadArtifactInventory(payload.sourceDir);
      await refreshRecentRuns();
    } catch (err) {
      patchState({
        bundle: null,
        model: null,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const openResultDir = async (path: string): Promise<void> => {
    if (!hasTauri || !path.trim()) {
      return;
    }
    try {
      await tauriInvoke<void>("open_result_dir", { path });
    } catch (err) {
      patchState({ error: err instanceof Error ? err.message : String(err) });
    }
  };

  const loadProjectJobs = async (): Promise<void> => {
    if (!hasTauri) {
      // surfaced in run control panel
      return;
    }
    const path = state.projectPath.trim();
    if (!path) {
      return;
    }
    patchState({ jobsLoading: true });
    try {
      const payload = await tauriInvoke<ProjectJobsResponse>("list_project_jobs", { projectPath: path });
      const selectedJobId = payload.jobs.length > 0 ? payload.jobs[0].id : "";
      patchState({
        jobsLoading: false,
        projectPath: payload.projectPath,
        projectName: payload.projectName ?? "",
        projectJobs: payload.jobs,
        selectedJobId,
      });
    } catch (err) {
      patchState({
        jobsLoading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const openProjectDocument = async (pathOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (pathOverride ?? state.projectPath).trim();
    if (!projectPath) {
      patchState({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patchState({ projectLifecycleLoading: true, projectLifecycleError: "", projectValidation: null });
    try {
      const doc = await tauriInvoke<ProjectDocument>("open_project_file", { projectPath });
      patchState({
        projectLifecycleLoading: false,
        projectDoc: doc,
        projectDocContent: doc.content,
        projectDocDirty: false,
        projectPath: doc.path,
        projectName: doc.name,
      });
      await loadProjectJobs();
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const initProjectDocument = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = state.projectPath.trim();
    if (!projectPath) {
      patchState({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patchState({ projectLifecycleLoading: true, projectLifecycleError: "", projectValidation: null });
    try {
      const doc = await tauriInvoke<ProjectDocument>("init_project_file", {
        projectPath,
        name: state.projectName.trim() ? state.projectName.trim() : null,
      });
      patchState({
        projectLifecycleLoading: false,
        projectDoc: doc,
        projectDocContent: doc.content,
        projectDocDirty: false,
        projectPath: doc.path,
        projectName: doc.name,
      });
      await loadProjectJobs();
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const saveProjectDocument = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = state.projectPath.trim();
    if (!projectPath) {
      patchState({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patchState({ projectLifecycleLoading: true, projectLifecycleError: "" });
    try {
      const doc = await tauriInvoke<ProjectDocument>("save_project_file", {
        projectPath,
        content: state.projectDocContent,
      });
      patchState({
        projectLifecycleLoading: false,
        projectDoc: doc,
        projectDocContent: doc.content,
        projectDocDirty: false,
        projectPath: doc.path,
        projectName: doc.name,
      });
      await loadProjectJobs();
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const validateProjectDocument = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = state.projectPath.trim();
    if (!projectPath) {
      patchState({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patchState({ projectLifecycleLoading: true, projectLifecycleError: "" });
    try {
      const validation = await tauriInvoke<ProjectValidationResult>("validate_project_file", {
        projectPath,
        jobId: state.selectedJobId.trim() ? state.selectedJobId.trim() : null,
      });
      patchState({
        projectLifecycleLoading: false,
        projectValidation: validation,
      });
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyGeometryResult = async (res: GeometryOperationResult): Promise<void> => {
    patchState({
      geomLoading: false,
      geomLogStdout: res.stdout,
      geomLogStderr: res.stderr,
      geomError: res.success ? "" : `Geometry operation failed (exit ${res.exitCode}).`,
    });
    if (res.project) {
      patchState({
        projectDoc: res.project,
        projectDocContent: res.project.content,
        projectDocDirty: false,
        projectPath: res.project.path,
        projectName: res.project.name,
      });
      await loadProjectJobs();
    }
  };

  const addRoomGeometry = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ geomError: "Geometry authoring requires Tauri runtime." });
      return;
    }
    const width = Number(state.geomRoomWidth);
    const length = Number(state.geomRoomLength);
    const height = Number(state.geomRoomHeight);
    const ox = Number(state.geomOriginX);
    const oy = Number(state.geomOriginY);
    const oz = Number(state.geomOriginZ);
    if (!Number.isFinite(width) || !Number.isFinite(length) || !Number.isFinite(height) || width <= 0 || length <= 0 || height <= 0) {
      patchState({ geomError: "Room dimensions must be positive numbers." });
      return;
    }
    patchState({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_room_to_project", {
        projectPath: state.projectPath,
        name: state.geomRoomName.trim() ? state.geomRoomName.trim() : null,
        width,
        length,
        height,
        originX: Number.isFinite(ox) ? ox : 0,
        originY: Number.isFinite(oy) ? oy : 0,
        originZ: Number.isFinite(oz) ? oz : 0,
        floorReflectance: null,
        wallReflectance: null,
        ceilingReflectance: null,
      });
      await applyGeometryResult(res);
    } catch (err) {
      patchState({
        geomLoading: false,
        geomError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const importGeometry = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ geomError: "Geometry authoring requires Tauri runtime." });
      return;
    }
    if (!state.geomImportPath.trim()) {
      patchState({ geomError: "Geometry import path is empty." });
      return;
    }
    patchState({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("import_geometry_to_project", {
        projectPath: state.projectPath,
        filePath: state.geomImportPath.trim(),
        format: state.geomImportFormat.trim() ? state.geomImportFormat.trim() : null,
      });
      await applyGeometryResult(res);
    } catch (err) {
      patchState({
        geomLoading: false,
        geomError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const cleanGeometry = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ geomError: "Geometry authoring requires Tauri runtime." });
      return;
    }
    const snap = Number(state.geomCleanSnapTolerance);
    if (!Number.isFinite(snap) || snap <= 0) {
      patchState({ geomError: "Snap tolerance must be a positive number." });
      return;
    }
    patchState({ geomLoading: true, geomError: "", geomLogStdout: "", geomLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("clean_geometry_in_project", {
        projectPath: state.projectPath,
        snapTolerance: snap,
        mergeCoplanar: state.geomCleanMergeCoplanar,
        detectRooms: state.geomCleanDetectRooms,
      });
      await applyGeometryResult(res);
    } catch (err) {
      patchState({
        geomLoading: false,
        geomError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyLuminaireResult = async (res: GeometryOperationResult): Promise<void> => {
    patchState({
      luminaireLoading: false,
      luminaireLogStdout: res.stdout,
      luminaireLogStderr: res.stderr,
      luminaireError: res.success ? "" : `Luminaire operation failed (exit ${res.exitCode}).`,
    });
    if (res.project) {
      patchState({
        projectDoc: res.project,
        projectDocContent: res.project.content,
        projectDocDirty: false,
        projectPath: res.project.path,
        projectName: res.project.name,
      });
      await loadProjectJobs();
    }
  };

  const addPhotometryAsset = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ luminaireError: "Luminaire authoring requires Tauri runtime." });
      return;
    }
    if (!state.photometryFilePath.trim()) {
      patchState({ luminaireError: "Photometry file path is empty." });
      return;
    }
    patchState({ luminaireLoading: true, luminaireError: "", luminaireLogStdout: "", luminaireLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_photometry_to_project", {
        projectPath: state.projectPath,
        filePath: state.photometryFilePath.trim(),
        assetId: state.photometryAssetId.trim() ? state.photometryAssetId.trim() : null,
        format: state.photometryFormat.trim() ? state.photometryFormat.trim() : null,
      });
      await applyLuminaireResult(res);
    } catch (err) {
      patchState({
        luminaireLoading: false,
        luminaireError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const addLuminaire = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ luminaireError: "Luminaire authoring requires Tauri runtime." });
      return;
    }
    if (!state.luminaireAssetId.trim()) {
      patchState({ luminaireError: "Luminaire asset id is required." });
      return;
    }
    const x = Number(state.luminaireX);
    const y = Number(state.luminaireY);
    const z = Number(state.luminaireZ);
    const yaw = Number(state.luminaireYaw);
    const pitch = Number(state.luminairePitch);
    const roll = Number(state.luminaireRoll);
    const maintenance = Number(state.luminaireMaintenance);
    const multiplier = Number(state.luminaireMultiplier);
    const tilt = Number(state.luminaireTilt);
    if (![x, y, z, yaw, pitch, roll, maintenance, multiplier, tilt].every(Number.isFinite)) {
      patchState({ luminaireError: "Luminaire numeric fields are invalid." });
      return;
    }
    patchState({ luminaireLoading: true, luminaireError: "", luminaireLogStdout: "", luminaireLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_luminaire_to_project", {
        projectPath: state.projectPath,
        assetId: state.luminaireAssetId.trim(),
        luminaireId: state.luminaireId.trim() ? state.luminaireId.trim() : null,
        name: state.luminaireName.trim() ? state.luminaireName.trim() : null,
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
      patchState({
        luminaireLoading: false,
        luminaireError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyCalcSetupResult = async (res: GeometryOperationResult): Promise<void> => {
    patchState({
      calcSetupLoading: false,
      calcSetupLogStdout: res.stdout,
      calcSetupLogStderr: res.stderr,
      calcSetupError: res.success ? "" : `Calculation setup operation failed (exit ${res.exitCode}).`,
    });
    if (res.project) {
      patchState({
        projectDoc: res.project,
        projectDocContent: res.project.content,
        projectDocDirty: false,
        projectPath: res.project.path,
        projectName: res.project.name,
      });
      await loadProjectJobs();
    }
  };

  const addGrid = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ calcSetupError: "Calculation setup requires Tauri runtime." });
      return;
    }
    const width = Number(state.gridWidth);
    const height = Number(state.gridHeight);
    const elevation = Number(state.gridElevation);
    const nx = Number(state.gridNx);
    const ny = Number(state.gridNy);
    const ox = Number(state.gridOriginX);
    const oy = Number(state.gridOriginY);
    const oz = Number(state.gridOriginZ);
    if (![width, height, elevation, nx, ny, ox, oy, oz].every(Number.isFinite) || width <= 0 || height <= 0 || nx < 2 || ny < 2) {
      patchState({ calcSetupError: "Grid inputs are invalid." });
      return;
    }
    patchState({ calcSetupLoading: true, calcSetupError: "", calcSetupLogStdout: "", calcSetupLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_grid_to_project", {
        projectPath: state.projectPath,
        name: state.gridName.trim() ? state.gridName.trim() : null,
        width,
        height,
        elevation,
        nx: Math.round(nx),
        ny: Math.round(ny),
        originX: ox,
        originY: oy,
        originZ: oz,
        roomId: state.gridRoomId.trim() ? state.gridRoomId.trim() : null,
      });
      await applyCalcSetupResult(res);
    } catch (err) {
      patchState({
        calcSetupLoading: false,
        calcSetupError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const addJob = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ calcSetupError: "Calculation setup requires Tauri runtime." });
      return;
    }
    if (!state.jobTypeInput.trim()) {
      patchState({ calcSetupError: "Job type is required." });
      return;
    }
    const seed = Number(state.jobSeedInput);
    if (!Number.isFinite(seed)) {
      patchState({ calcSetupError: "Job seed is invalid." });
      return;
    }
    patchState({ calcSetupLoading: true, calcSetupError: "", calcSetupLogStdout: "", calcSetupLogStderr: "" });
    try {
      const res = await tauriInvoke<GeometryOperationResult>("add_job_to_project", {
        projectPath: state.projectPath,
        jobId: state.jobIdInput.trim() ? state.jobIdInput.trim() : null,
        jobType: state.jobTypeInput.trim(),
        backend: state.jobBackendInput.trim() ? state.jobBackendInput.trim() : "cpu",
        seed: Math.round(seed),
      });
      await applyCalcSetupResult(res);
    } catch (err) {
      patchState({
        calcSetupLoading: false,
        calcSetupError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const runExportAction = async (cmd: "export_debug_bundle" | "export_client_bundle" | "export_backend_compare" | "export_roadway_report"): Promise<void> => {
    if (!hasTauri) {
      patchState({ exportError: "Export requires Tauri runtime." });
      return;
    }
    const jobId = (state.exportJobId || state.selectedJobId).trim();
    if (!jobId) {
      patchState({ exportError: "Export job id is required." });
      return;
    }
    const out = state.exportOutputPath.trim();
    if (!out) {
      patchState({ exportError: "Export output path is required." });
      return;
    }
    patchState({ exportLoading: true, exportError: "", exportLogStdout: "", exportLogStderr: "" });
    try {
      const res = await tauriInvoke<ExportOperationResult>(cmd, {
        projectPath: state.projectPath,
        jobId,
        outputPath: out,
      });
      patchState({
        exportLoading: false,
        exportLogStdout: res.stdout,
        exportLogStderr: res.stderr,
        exportError: res.success ? "" : `Export failed (exit ${res.exitCode})`,
        exportOutputPath: res.outputPath,
      });
    } catch (err) {
      patchState({
        exportLoading: false,
        exportError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const runAgentIntent = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ agentError: "Agent runtime requires Tauri runtime." });
      return;
    }
    if (!state.projectPath.trim()) {
      patchState({ agentError: "Project path is required for agent runtime." });
      return;
    }
    if (!state.agentIntent.trim()) {
      patchState({ agentError: "Agent intent is empty." });
      return;
    }
    patchState({ agentLoading: true, agentError: "", agentResponse: null });
    try {
      const payload = await tauriInvoke<{ response: Record<string, unknown> }>("execute_agent_intent", {
        projectPath: state.projectPath,
        intent: state.agentIntent,
        approvalsJson: state.agentApprovalsJson,
      });
      patchState({
        agentLoading: false,
        agentResponse: payload.response,
      });
      await openProjectDocument(state.projectPath);
    } catch (err) {
      patchState({
        agentLoading: false,
        agentError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const runner = useJobRunner({
    hasTauri,
    projectPath: state.projectPath,
    selectedJobId: state.selectedJobId,
    projectName: state.projectName,
    onResultDir: async (resultDir) => {
      await loadOutputs(resultDir);
    },
    onNoResultDir: async () => {
      await refreshRecentRuns();
    },
  });

  useEffect(() => {
    void refreshRecentRuns();
    void loadContract();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summaryPanel = model ? (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
      <MetricCard label="Mean Lux" value={fmt(model.summary.meanLux)} />
      <MetricCard label="Min Lux" value={fmt(model.summary.minLux)} />
      <MetricCard label="Max Lux" value={fmt(model.summary.maxLux)} />
      <MetricCard label="Uniformity" value={fmt(model.summary.uniformityRatio, 3)} />
      <MetricCard label="Highest UGR" value={fmt(model.summary.highestUgr)} />
      <MetricCard label="Contract" value={model.contractVersion} />
    </div>
  ) : (
    <div className="rounded-md border border-border bg-panelSoft/50 p-3 text-sm text-muted">
      No backend result loaded.
    </div>
  );

  const complianceTone =
    model?.compliance.status === "PASS"
      ? "text-emerald-300"
      : model?.compliance.status === "FAIL"
        ? "text-rose-300"
        : "text-amber-200";

  return (
    <AppShell
      sidebar={
        <Sidebar title="Project">
          <SidebarSection title="Navigator">
            {projectItems.map((item) => (
              <ToolbarButton key={item} className="w-full text-left">
                {item}
              </ToolbarButton>
            ))}
          </SidebarSection>
        </Sidebar>
      }
      viewport={
        <div>
          <div className="lux-panel-title">Result Mapping</div>
          <div className="m-4 h-[calc(100%-2rem)] space-y-4 overflow-auto rounded-lg border border-border bg-panelSoft/60 p-4">
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Viewport Link</div>
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-[2fr_1fr]">
                <div className="rounded border border-border/60 bg-panelSoft/50 p-2">
                  <svg viewBox="0 0 100 70" className="h-44 w-full rounded bg-panel">
                    <rect x="0" y="0" width="100" height="70" fill="transparent" stroke="rgba(120,130,150,0.4)" />
                    {viewportPoints.length > 0 && viewportBounds
                      ? viewportPoints.map((p, i) => {
                          const spanX = Math.max(viewportBounds.maxX - viewportBounds.minX, 1e-9);
                          const spanY = Math.max(viewportBounds.maxY - viewportBounds.minY, 1e-9);
                          const px = 6 + ((p.x - viewportBounds.minX) / spanX) * 88;
                          const py = 64 - ((p.y - viewportBounds.minY) / spanY) * 58;
                          const isSelected = selectedPoint && Math.abs(selectedPoint.x - p.x) < 1e-9 && Math.abs(selectedPoint.y - p.y) < 1e-9;
                          return (
                            <circle
                              key={`${p.label}-${i}`}
                              cx={px}
                              cy={py}
                              r={isSelected ? 2.6 : 1.6}
                              fill={isSelected ? "#60a5fa" : "#94a3b8"}
                            />
                          );
                        })
                      : null}
                  </svg>
                </div>
                <div className="space-y-2 text-xs text-muted">
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Source Table: {state.selectedTableTitle || "None"}
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Selected Row: {state.selectedRowIndex >= 0 ? String(state.selectedRowIndex + 1) : "None"}
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Coordinates:{" "}
                    {selectedPoint
                      ? `x=${selectedPoint.x.toFixed(3)}, y=${selectedPoint.y.toFixed(3)}${
                          selectedPoint.z !== undefined ? `, z=${selectedPoint.z.toFixed(3)}` : ""
                        }`
                      : "N/A"}
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Rows Plotted: {String(viewportPoints.length)}
                  </div>
                </div>
              </div>
            </section>
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-[2fr_1fr]">
              <label className="block">
                <span className="mb-1 block text-xs uppercase tracking-[0.12em] text-muted">Result Directory</span>
                <input
                  value={state.resultDir}
                  onChange={(e) => patchState({ resultDir: e.target.value })}
                  placeholder="Absolute path to job output folder (contains result.json)"
                  className="w-full rounded-md border border-border bg-panel px-3 py-2 text-sm text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
              </label>
              <div className="flex items-end gap-2">
                <ToolbarButton onClick={() => void loadOutputs(state.resultDir)} disabled={state.loading} className="w-full">
                  {state.loading ? "Loading..." : "Load Path"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void loadOutputs()} disabled={state.loading} className="w-full">
                  Load Latest Out
                </ToolbarButton>
                <ToolbarButton onClick={() => void refreshRecentRuns()} disabled={state.recentLoading} className="w-full">
                  {state.recentLoading ? "Refreshing..." : "Refresh Runs"}
                </ToolbarButton>
              </div>
            </div>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Project Lifecycle</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.projectPath}
                  onChange={(e) => patchState({ projectPath: e.target.value })}
                  placeholder="Project file path (.json)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <input
                  value={state.projectName}
                  onChange={(e) => patchState({ projectName: e.target.value })}
                  placeholder="Project name (for init)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void initProjectDocument()} disabled={state.projectLifecycleLoading}>
                  {state.projectLifecycleLoading ? "Working..." : "New"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void openProjectDocument()} disabled={state.projectLifecycleLoading}>
                  Open
                </ToolbarButton>
                <ToolbarButton onClick={() => void saveProjectDocument()} disabled={state.projectLifecycleLoading || !state.projectDocDirty}>
                  Save
                </ToolbarButton>
                <ToolbarButton onClick={() => void validateProjectDocument()} disabled={state.projectLifecycleLoading}>
                  Validate
                </ToolbarButton>
              </div>
              {state.projectLifecycleError ? <div className="mb-2 text-xs text-rose-300">{state.projectLifecycleError}</div> : null}
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-4">
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Loaded: {state.projectDoc ? state.projectDoc.path : "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Schema: {state.projectDoc ? String(state.projectDoc.schemaVersion) : "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Jobs: {state.projectDoc ? String(state.projectDoc.jobCount) : "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Dirty: {state.projectDocDirty ? "yes" : "no"}
                </div>
              </div>
              <textarea
                value={state.projectDocContent}
                onChange={(e) => patchState({ projectDocContent: e.target.value, projectDocDirty: true })}
                placeholder="Project JSON editor"
                className="min-h-36 w-full rounded border border-border bg-panelSoft/50 px-2 py-2 font-mono text-[11px] text-text outline-none focus:ring-2 focus:ring-blue-400/30"
              />
              {state.projectValidation ? (
                <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                  <div className="text-text">
                    Validation: {state.projectValidation.valid ? "PASS" : "FAIL"} / checked jobs: {state.projectValidation.checkedJobs}
                  </div>
                  {state.projectValidation.warnings.length > 0 ? (
                    <div className="mt-1 text-amber-200">{state.projectValidation.warnings.join(" | ")}</div>
                  ) : null}
                  {state.projectValidation.errors.length > 0 ? (
                    <div className="mt-1 text-rose-300">{state.projectValidation.errors.join(" | ")}</div>
                  ) : null}
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Geometry Authoring</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.geomRoomName}
                  onChange={(e) => patchState({ geomRoomName: e.target.value })}
                  placeholder="Room name"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomRoomWidth}
                  onChange={(e) => patchState({ geomRoomWidth: e.target.value })}
                  placeholder="Width"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomRoomLength}
                  onChange={(e) => patchState({ geomRoomLength: e.target.value })}
                  placeholder="Length"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomRoomHeight}
                  onChange={(e) => patchState({ geomRoomHeight: e.target.value })}
                  placeholder="Height"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomOriginX}
                  onChange={(e) => patchState({ geomOriginX: e.target.value })}
                  placeholder="Origin X"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomOriginY}
                  onChange={(e) => patchState({ geomOriginY: e.target.value })}
                  placeholder="Origin Y"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomOriginZ}
                  onChange={(e) => patchState({ geomOriginZ: e.target.value })}
                  placeholder="Origin Z"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void addRoomGeometry()} disabled={state.geomLoading}>
                  {state.geomLoading ? "Working..." : "Add Room"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr]">
                <input
                  value={state.geomImportPath}
                  onChange={(e) => patchState({ geomImportPath: e.target.value })}
                  placeholder="Geometry file path (DXF/OBJ/GLTF/FBX/SKP/IFC/DWG)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.geomImportFormat}
                  onChange={(e) => patchState({ geomImportFormat: e.target.value })}
                  placeholder="Optional format override"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void importGeometry()} disabled={state.geomLoading}>
                  {state.geomLoading ? "Working..." : "Import Geometry"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr]">
                <input
                  value={state.geomCleanSnapTolerance}
                  onChange={(e) => patchState({ geomCleanSnapTolerance: e.target.value })}
                  placeholder="Snap tolerance"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={state.geomCleanDetectRooms}
                    onChange={(e) => patchState({ geomCleanDetectRooms: e.target.checked })}
                  />
                  Detect rooms
                </label>
                <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={state.geomCleanMergeCoplanar}
                    onChange={(e) => patchState({ geomCleanMergeCoplanar: e.target.checked })}
                  />
                  Merge coplanar
                </label>
                <ToolbarButton onClick={() => void cleanGeometry()} disabled={state.geomLoading}>
                  {state.geomLoading ? "Working..." : "Clean Geometry"}
                </ToolbarButton>
              </div>
              {state.geomError ? <div className="mb-2 text-xs text-rose-300">{state.geomError}</div> : null}
              {(state.geomLogStdout || state.geomLogStderr) ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Geometry stdout</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.geomLogStdout || "(empty)"}</pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Geometry stderr</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.geomLogStderr || "(empty)"}</pre>
                  </div>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Luminaire Authoring</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
                <input
                  value={state.photometryFilePath}
                  onChange={(e) => patchState({ photometryFilePath: e.target.value })}
                  placeholder="Photometry file path (.ies/.ldt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.photometryAssetId}
                  onChange={(e) => patchState({ photometryAssetId: e.target.value })}
                  placeholder="Optional asset id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.photometryFormat}
                  onChange={(e) => patchState({ photometryFormat: e.target.value })}
                  placeholder="Optional format (IES/LDT)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void addPhotometryAsset()} disabled={state.luminaireLoading}>
                  {state.luminaireLoading ? "Working..." : "Add Photometry"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.luminaireAssetId}
                  onChange={(e) => patchState({ luminaireAssetId: e.target.value })}
                  placeholder="Asset id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireId}
                  onChange={(e) => patchState({ luminaireId: e.target.value })}
                  placeholder="Optional luminaire id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireName}
                  onChange={(e) => patchState({ luminaireName: e.target.value })}
                  placeholder="Optional luminaire name"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireX}
                  onChange={(e) => patchState({ luminaireX: e.target.value })}
                  placeholder="X"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireY}
                  onChange={(e) => patchState({ luminaireY: e.target.value })}
                  placeholder="Y"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireZ}
                  onChange={(e) => patchState({ luminaireZ: e.target.value })}
                  placeholder="Z"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireYaw}
                  onChange={(e) => patchState({ luminaireYaw: e.target.value })}
                  placeholder="Yaw"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void addLuminaire()} disabled={state.luminaireLoading}>
                  {state.luminaireLoading ? "Working..." : "Add Luminaire"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.luminairePitch}
                  onChange={(e) => patchState({ luminairePitch: e.target.value })}
                  placeholder="Pitch"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireRoll}
                  onChange={(e) => patchState({ luminaireRoll: e.target.value })}
                  placeholder="Roll"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireMaintenance}
                  onChange={(e) => patchState({ luminaireMaintenance: e.target.value })}
                  placeholder="Maintenance"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireMultiplier}
                  onChange={(e) => patchState({ luminaireMultiplier: e.target.value })}
                  placeholder="Multiplier"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.luminaireTilt}
                  onChange={(e) => patchState({ luminaireTilt: e.target.value })}
                  placeholder="Tilt"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
              </div>
              {state.luminaireError ? <div className="mb-2 text-xs text-rose-300">{state.luminaireError}</div> : null}
              {(state.luminaireLogStdout || state.luminaireLogStderr) ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Luminaire stdout</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.luminaireLogStdout || "(empty)"}</pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Luminaire stderr</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.luminaireLogStderr || "(empty)"}</pre>
                  </div>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Calculation Setup</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.gridName}
                  onChange={(e) => patchState({ gridName: e.target.value })}
                  placeholder="Grid name"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input value={state.gridWidth} onChange={(e) => patchState({ gridWidth: e.target.value })} placeholder="Width" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridHeight} onChange={(e) => patchState({ gridHeight: e.target.value })} placeholder="Height" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridElevation} onChange={(e) => patchState({ gridElevation: e.target.value })} placeholder="Elevation" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridNx} onChange={(e) => patchState({ gridNx: e.target.value })} placeholder="NX" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridNy} onChange={(e) => patchState({ gridNy: e.target.value })} placeholder="NY" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridOriginX} onChange={(e) => patchState({ gridOriginX: e.target.value })} placeholder="Origin X" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridOriginY} onChange={(e) => patchState({ gridOriginY: e.target.value })} placeholder="Origin Y" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridOriginZ} onChange={(e) => patchState({ gridOriginZ: e.target.value })} placeholder="Origin Z" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.gridRoomId} onChange={(e) => patchState({ gridRoomId: e.target.value })} placeholder="Room id (opt)" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <ToolbarButton onClick={() => void addGrid()} disabled={state.calcSetupLoading}>
                  {state.calcSetupLoading ? "Working..." : "Add Grid"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr]">
                <input value={state.jobIdInput} onChange={(e) => patchState({ jobIdInput: e.target.value })} placeholder="Job id (opt)" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.jobTypeInput} onChange={(e) => patchState({ jobTypeInput: e.target.value })} placeholder="Job type (direct/radiosity/...)" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.jobBackendInput} onChange={(e) => patchState({ jobBackendInput: e.target.value })} placeholder="Backend (cpu/df/radiance)" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <input value={state.jobSeedInput} onChange={(e) => patchState({ jobSeedInput: e.target.value })} placeholder="Seed" className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none" />
                <ToolbarButton onClick={() => void addJob()} disabled={state.calcSetupLoading}>
                  {state.calcSetupLoading ? "Working..." : "Add Job"}
                </ToolbarButton>
              </div>
              {state.calcSetupError ? <div className="mb-2 text-xs text-rose-300">{state.calcSetupError}</div> : null}
              {(state.calcSetupLogStdout || state.calcSetupLogStderr) ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Setup stdout</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.calcSetupLogStdout || "(empty)"}</pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Setup stderr</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.calcSetupLogStderr || "(empty)"}</pre>
                  </div>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Export / Reporting</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.exportJobId}
                  onChange={(e) => patchState({ exportJobId: e.target.value })}
                  placeholder={`Job id (default: ${state.selectedJobId || "selected"})`}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.exportOutputPath}
                  onChange={(e) => patchState({ exportOutputPath: e.target.value })}
                  placeholder="Output file path"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void runExportAction("export_debug_bundle")} disabled={state.exportLoading}>
                  Debug Bundle
                </ToolbarButton>
                <ToolbarButton onClick={() => void runExportAction("export_client_bundle")} disabled={state.exportLoading}>
                  Client Bundle
                </ToolbarButton>
                <ToolbarButton onClick={() => void runExportAction("export_backend_compare")} disabled={state.exportLoading}>
                  Backend Compare
                </ToolbarButton>
                <ToolbarButton onClick={() => void runExportAction("export_roadway_report")} disabled={state.exportLoading}>
                  Roadway Report
                </ToolbarButton>
              </div>
              {state.exportError ? <div className="mb-2 text-xs text-rose-300">{state.exportError}</div> : null}
              {(state.exportLogStdout || state.exportLogStderr) ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Export stdout</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.exportLogStdout || "(empty)"}</pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">Export stderr</div>
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap">{state.exportLogStderr || "(empty)"}</pre>
                  </div>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Agent Console</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[3fr_2fr_1fr]">
                <input
                  value={state.agentIntent}
                  onChange={(e) => patchState({ agentIntent: e.target.value })}
                  placeholder='Intent (example: "import file.dxf detect rooms and add grid")'
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.agentApprovalsJson}
                  onChange={(e) => patchState({ agentApprovalsJson: e.target.value })}
                  placeholder='Approvals JSON (example: {"apply_diff":true,"run_job":true})'
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 font-mono text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void runAgentIntent()} disabled={state.agentLoading}>
                  {state.agentLoading ? "Running..." : "Execute Intent"}
                </ToolbarButton>
              </div>
              {state.agentError ? <div className="mb-2 text-xs text-rose-300">{state.agentError}</div> : null}
              {state.agentResponse ? (
                <div className="space-y-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                    Plan: {(state.agentResponse.plan as string) ?? "N/A"}
                  </div>
                  <DataTable title="Agent Response Paths" rows={agentResponseRows} />
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Run Control</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr]">
                <input
                  value={state.projectPath}
                  onChange={(e) => patchState({ projectPath: e.target.value })}
                  placeholder="Project file path (.json)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void loadProjectJobs()} disabled={state.jobsLoading || runner.runLoading}>
                  {state.jobsLoading ? "Loading Jobs..." : "Load Jobs"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void runner.runSelectedJob()} disabled={runner.runLoading || state.jobsLoading}>
                  {runner.runLoading ? "Running..." : "Run Selected Job"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void runner.cancelActiveRun()} disabled={!runner.runLoading || runner.activeRunId === null}>
                  Cancel
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
                <select
                  value={state.selectedJobId}
                  onChange={(e) => patchState({ selectedJobId: e.target.value })}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                >
                  {state.projectJobs.length > 0 ? (
                    state.projectJobs.map((job) => (
                      <option key={job.id} value={job.id}>
                        {job.id} ({job.jobType}/{job.backend})
                      </option>
                    ))
                  ) : (
                    <option value="">No jobs loaded</option>
                  )}
                </select>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Project: {state.projectName || "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Jobs: {state.projectJobs.length}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Last exit: {runner.runResult ? String(runner.runResult.exitCode) : "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Status: {runner.runStatus}
                </div>
              </div>
              {runner.runError ? <div className="mb-2 text-xs text-rose-300">{runner.runError}</div> : null}
              {runner.runLoading || runner.runResult ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">stdout</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap">
                      {(runner.runLoading ? runner.runStdout : runner.runResult?.stdout) || "(empty)"}
                    </pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">stderr</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap">
                      {(runner.runLoading ? runner.runStderr : runner.runResult?.stderr) || "(empty)"}
                    </pre>
                  </div>
                </div>
              ) : null}
              {runner.runTimeline.length > 0 ? (
                <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                  <div className="mb-1 text-text">Run Timeline</div>
                  <div className="max-h-32 space-y-1 overflow-auto">
                    {runner.runTimeline
                      .slice()
                      .reverse()
                      .slice(0, 24)
                      .map((event, idx) => (
                        <div key={`${event.atUnixMs}-${idx}`} className="rounded border border-border/60 bg-panel px-2 py-1">
                          <span className="text-text">{new Date(event.atUnixMs).toLocaleTimeString()}</span> [{event.status}]{" "}
                          {event.message}
                        </div>
                      ))}
                  </div>
                </div>
              ) : null}
              {runner.runHistory.length > 0 ? (
                <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                  <div className="mb-1 text-text">Run History</div>
                  <div className="max-h-48 space-y-1 overflow-auto">
                    {runner.runHistory.map((entry) => (
                      <div key={entry.localId} className="rounded border border-border/60 bg-panel px-2 py-1">
                        <div className="truncate text-text">
                          {entry.jobId} [{entry.status}] {entry.exitCode !== null ? `exit ${entry.exitCode}` : ""}
                        </div>
                        <div className="truncate">
                          {entry.projectName || "Project"} • {entry.projectPath}
                        </div>
                        <div>
                          {new Date(entry.startedAtUnixMs).toLocaleString()}
                          {entry.endedAtUnixMs ? ` -> ${new Date(entry.endedAtUnixMs).toLocaleString()}` : ""}
                        </div>
                        <div className="mt-1 flex gap-2">
                          <ToolbarButton
                            onClick={() => {
                              if (entry.resultDir) {
                                void loadOutputs(entry.resultDir);
                              }
                            }}
                            disabled={!entry.resultDir}
                            className="w-full"
                          >
                            Load
                          </ToolbarButton>
                          <ToolbarButton
                            onClick={() => {
                              if (entry.resultDir) {
                                void openResultDir(entry.resultDir);
                              }
                            }}
                            disabled={!entry.resultDir}
                            className="w-full"
                          >
                            Open Dir
                          </ToolbarButton>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
            {state.error ? (
              <div className="rounded-md border border-rose-500/40 bg-rose-950/30 p-3 text-sm text-rose-200">{state.error}</div>
            ) : null}
            {model?.contractIssues.length ? (
              <section className="rounded-md border border-amber-500/40 bg-amber-950/25 p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-amber-200">Contract Issues</div>
                <ul className="space-y-1 text-xs text-amber-100">
                  {model.contractIssues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {summaryPanel}
            {model?.radiosity.available ? (
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Radiosity Diagnostics</div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  <MetricCard label="Converged" value={String(model.radiosity.converged ?? "N/A")} />
                  <MetricCard label="Iterations" value={fmt(model.radiosity.iterations)} />
                  <MetricCard label="Stop Reason" value={model.radiosity.stopReason ?? "N/A"} />
                  <MetricCard
                    label="Last Residual"
                    value={
                      model.radiosity.residuals.length > 0
                        ? model.radiosity.residuals[model.radiosity.residuals.length - 1].toExponential(3)
                        : "N/A"
                    }
                  />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Radiosity Solver Status" rows={objectToRows(model.radiosity.solverStatus)} />
                  <DataTable title="Radiosity Energy" rows={objectToRows(model.radiosity.energy)} />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Radiosity Diagnostics" rows={objectToRows(model.radiosity.diagnostics)} />
                  <DataTable
                    title="Radiosity Quality Flags"
                    rows={[
                      {
                        residual_threshold: model.radiosity.residualThreshold ?? "N/A",
                        residual_below_threshold: model.radiosity.residualBelowThreshold ?? "N/A",
                        residual_nonincreasing: model.radiosity.residualNonincreasing ?? "N/A",
                      },
                    ]}
                  />
                </div>
                {model.radiosity.residuals.length > 0 ? (
                  <DataTable
                    title="Radiosity Residual Trace"
                    rows={model.radiosity.residuals.map((value, index) => ({ iteration: index + 1, residual: value }))}
                  />
                ) : null}
                {model.radiosity.energyBalanceHistory.length > 0 ? (
                  <DataTable
                    title="Radiosity Energy Balance Trace"
                    rows={model.radiosity.energyBalanceHistory.map((value, index) => ({
                      iteration: index + 1,
                      energy_balance_rel: value,
                    }))}
                  />
                ) : null}
              </section>
            ) : null}

            {model?.ugr.available ? (
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">UGR Diagnostics</div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
                  <MetricCard label="Worst Case UGR" value={fmt(model.ugr.worstCase)} />
                  <MetricCard label="UGR Views" value={String(model.ugr.views.length)} />
                  <MetricCard label="UGR Debug" value={model.ugr.debug ? "Present" : "Absent"} />
                  <MetricCard label="Debug Contributors" value={String(model.ugr.debugTopContributors.length)} />
                  <MetricCard label="View Contributors" value={String(model.ugr.viewTopContributors.length)} />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable
                    title="UGR Views"
                    rows={model.ugr.views}
                    onSelectRow={selectRow}
                    selectedTableTitle={state.selectedTableTitle}
                    selectedRowIndex={state.selectedRowIndex}
                  />
                  <DataTable title="UGR Debug" rows={objectToRows(model.ugr.debug)} />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="UGR Debug Top Contributors" rows={model.ugr.debugTopContributors} />
                  <DataTable title="UGR View Top Contributors" rows={model.ugr.viewTopContributors} />
                </div>
              </section>
            ) : null}

            {model?.roadway.available ? (
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Roadway Diagnostics</div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  <MetricCard label="Road Class" value={model.roadway.roadClass ?? "N/A"} />
                  <MetricCard label="Profile Present" value={model.roadway.roadwayProfile ? "Yes" : "No"} />
                  <MetricCard label="Roadway Block" value={model.roadway.roadway ? "Yes" : "No"} />
                  <MetricCard label="Glare Views" value={String(model.roadway.observerGlareViews.length)} />
                  <MetricCard label="Lane Metrics" value={String(model.roadway.laneMetrics.length)} />
                  <MetricCard label="Observer Views" value={String(model.roadway.observerLuminanceViews.length)} />
                  <MetricCard label="TI Observers" value={String(model.roadway.tiObservers.length)} />
                  <MetricCard label="Compliance" value={model.roadway.compliance ? "Present" : "Absent"} />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Roadway Profile" rows={objectToRows(model.roadway.roadwayProfile)} />
                  <DataTable title="Roadway Summary Block" rows={objectToRows(model.roadway.roadway)} />
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Roadway Compliance" rows={objectToRows(model.roadway.compliance)} />
                  <DataTable title="Roadway Luminance Model" rows={objectToRows(model.roadway.luminanceModel)} />
                </div>
                <DataTable
                  title="Roadway Lane Metrics"
                  rows={model.roadway.laneMetrics}
                  onSelectRow={selectRow}
                  selectedTableTitle={state.selectedTableTitle}
                  selectedRowIndex={state.selectedRowIndex}
                />
                <DataTable
                  title="Roadway Observer Luminance Views"
                  rows={model.roadway.observerLuminanceViews}
                  onSelectRow={selectRow}
                  selectedTableTitle={state.selectedTableTitle}
                  selectedRowIndex={state.selectedRowIndex}
                />
                <DataTable title="Roadway TI Observers" rows={model.roadway.tiObservers} />
                <DataTable
                  title="Roadway Observer Glare Views"
                  rows={model.roadway.observerGlareViews}
                  onSelectRow={selectRow}
                  selectedTableTitle={state.selectedTableTitle}
                  selectedRowIndex={state.selectedRowIndex}
                />
              </section>
            ) : null}

            {model?.roadwaySubmission.available ? (
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Roadway Submission (Typed)</div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  <MetricCard label="Source" value={model.roadwaySubmission.source} />
                  <MetricCard label="Status" value={model.roadwaySubmission.status ?? "N/A"} />
                  <MetricCard label="Checks" value={String(model.roadwaySubmission.checks.length)} />
                  <MetricCard label="Validation Issues" value={String(model.roadwaySubmission.validationIssues.length)} />
                </div>
                {model.roadwaySubmission.title ? (
                  <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-text">
                    {model.roadwaySubmission.title}
                  </div>
                ) : null}
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Submission Profile" rows={objectToRows(model.roadwaySubmission.profile)} />
                  <DataTable title="Submission Overall" rows={objectToRows(model.roadwaySubmission.overall)} />
                </div>
                <DataTable title="Submission Checks" rows={model.roadwaySubmission.checks} />
                {model.roadwaySubmission.validationIssues.length > 0 ? (
                  <div className="mt-2 rounded border border-amber-500/40 bg-amber-950/25 p-2 text-xs text-amber-100">
                    {model.roadwaySubmission.validationIssues.map((issue) => (
                      <div key={issue}>{issue}</div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 rounded border border-emerald-500/40 bg-emerald-950/25 p-2 text-xs text-emerald-100">
                    Submission payload validated against required typed fields.
                  </div>
                )}
              </section>
            ) : null}

            {model?.engines.available ? (
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Results Engines</div>
                <DataTable title="Engines and Summary Keys" rows={model.engines.summaries} />
              </section>
            ) : null}

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Compliance</div>
                <div className={`text-sm font-semibold ${complianceTone}`}>{model?.compliance.status ?? "N/A"}</div>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {(model?.compliance.reasons ?? []).length > 0 ? (
                    (model?.compliance.reasons ?? []).map((reason) => <li key={reason}>{reason}</li>)
                  ) : (
                    <li>No compliance reasons reported.</li>
                  )}
                </ul>
              </section>
              <section className="rounded-md border border-border bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Tables</div>
                <div className="space-y-1 text-sm text-text">
                  <div>Grids: {model?.tableCounts.grids ?? 0}</div>
                  <div>Vertical planes: {model?.tableCounts.verticalPlanes ?? 0}</div>
                  <div>Point sets: {model?.tableCounts.pointSets ?? 0}</div>
                </div>
              </section>
            </div>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Recent Runs</div>
              <div className="space-y-1 text-xs text-muted">
                {state.recentRuns.length > 0 ? (
                  state.recentRuns.map((run) => (
                    <div key={`${run.resultDir}-${run.modifiedUnixS}`} className="rounded border border-border/60 bg-panelSoft/50 p-2">
                      <div className="truncate text-text">{run.resultDir}</div>
                      <div>{run.jobType ?? "unknown"} / {run.jobId ?? "unknown"} / {run.contractVersion ?? "unknown"}</div>
                      <div>{fmtUnix(run.modifiedUnixS)}</div>
                      <div className="mt-1 flex gap-2">
                        <ToolbarButton onClick={() => void loadOutputs(run.resultDir)} className="w-full">Load</ToolbarButton>
                        <ToolbarButton onClick={() => void openResultDir(run.resultDir)} className="w-full">Open Dir</ToolbarButton>
                      </div>
                    </div>
                  ))
                ) : (
                  <div>No runs detected in `out/`.</div>
                )}
              </div>
            </section>
            <DataTable
              title="Grids"
              rows={(model?.tables.grids ?? []) as JsonRow[]}
              onSelectRow={selectRow}
              selectedTableTitle={state.selectedTableTitle}
              selectedRowIndex={state.selectedRowIndex}
            />
            <DataTable
              title="Vertical Planes"
              rows={(model?.tables.verticalPlanes ?? []) as JsonRow[]}
              onSelectRow={selectRow}
              selectedTableTitle={state.selectedTableTitle}
              selectedRowIndex={state.selectedRowIndex}
            />
            <DataTable
              title="Point Sets"
              rows={(model?.tables.pointSets ?? []) as JsonRow[]}
              onSelectRow={selectRow}
              selectedTableTitle={state.selectedTableTitle}
              selectedRowIndex={state.selectedRowIndex}
            />
            <DataTable title="Indoor Planes" rows={(model?.indoorPlanes ?? []) as JsonRow[]} />
            <DataTable title="Zone Metrics" rows={(model?.zoneMetrics ?? []) as JsonRow[]} />
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Artifact Inventory</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr]">
                <ToolbarButton
                  onClick={() => void artifacts.loadArtifactInventory(state.resultDir)}
                  disabled={artifacts.artifactListLoading || !state.resultDir.trim()}
                >
                  {artifacts.artifactListLoading ? "Refreshing..." : "Refresh Artifacts"}
                </ToolbarButton>
                <select
                  value={artifacts.selectedArtifactPath}
                  onChange={(e) => artifacts.setSelectedArtifactPath(e.target.value)}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                >
                  {artifacts.artifactList.length > 0 ? (
                    artifacts.artifactList.map((entry) => (
                      <option key={entry.path} value={entry.path}>
                        {entry.relativePath}
                      </option>
                    ))
                  ) : (
                    <option value="">No artifacts listed</option>
                  )}
                </select>
                <ToolbarButton onClick={() => void artifacts.readSelectedArtifact()} disabled={artifacts.artifactLoading || !artifacts.selectedArtifactPath}>
                  {artifacts.artifactLoading ? "Reading..." : "Read Selected"}
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => void artifacts.previewSelectedArtifact()}
                  disabled={artifacts.artifactBinaryLoading || !artifacts.selectedArtifactPath}
                >
                  {artifacts.artifactBinaryLoading ? "Previewing..." : "Preview Selected"}
                </ToolbarButton>
              </div>
              {artifacts.artifactListError ? <div className="mb-2 text-xs text-rose-300">{artifacts.artifactListError}</div> : null}
              <DataTable
                title="Artifacts"
                rows={artifacts.artifactList.map((entry) => ({
                  relative_path: entry.relativePath,
                  size_bytes: entry.sizeBytes,
                  modified: fmtUnix(entry.modifiedUnixS),
                }))}
              />
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Artifact Reader</div>
              <div className="mb-2 flex gap-2">
                <input
                  value={artifacts.artifactPath}
                  onChange={(e) => artifacts.setArtifactPath(e.target.value)}
                  placeholder="Path to artifact file"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void artifacts.readArtifact()} disabled={artifacts.artifactLoading}>
                  {artifacts.artifactLoading ? "Reading..." : "Read"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void artifacts.readArtifactBinaryAtPath(artifacts.artifactPath)} disabled={artifacts.artifactBinaryLoading}>
                  {artifacts.artifactBinaryLoading ? "Previewing..." : "Preview"}
                </ToolbarButton>
              </div>
              {artifacts.artifactError ? <div className="mb-2 text-xs text-rose-300">{artifacts.artifactError}</div> : null}
              {artifacts.artifact ? (
                <div className="text-xs text-muted">
                  <div className="mb-1">{artifacts.artifact.path} ({artifacts.artifact.sizeBytes} bytes){artifacts.artifact.truncated ? " [truncated]" : ""}</div>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-border/60 bg-panelSoft/50 p-2 text-[11px] text-text">
                    {artifacts.artifact.content}
                  </pre>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Artifact Image Preview</div>
              {artifacts.artifactBinary ? (
                <div className="text-xs text-muted">
                  <div className="mb-2">
                    {artifacts.artifactBinary.path} ({artifacts.artifactBinary.sizeBytes} bytes){artifacts.artifactBinary.truncated ? " [truncated]" : ""}{" "}
                    / {artifacts.artifactBinary.mimeType}
                  </div>
                  {artifacts.artifactBinary.mimeType.startsWith("image/") ? (
                    <img
                      src={`data:${artifacts.artifactBinary.mimeType};base64,${artifacts.artifactBinary.dataBase64}`}
                      alt="Artifact preview"
                      className="max-h-[420px] rounded border border-border/60 bg-panelSoft/50"
                    />
                  ) : (
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                      Selected artifact is not a supported image type.
                    </div>
                  )}
                </div>
              ) : (
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Select an artifact and click Preview to render image outputs (PNG/JPG/WebP/GIF/SVG).
                </div>
              )}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Raw JSON Explorer</div>
              <div className="mb-2 text-xs text-muted">
                Flattened field view of raw payloads from `result.json`, `tables.json`, and `results.json`.
              </div>
              <DataTable title="Raw Result JSON Paths" rows={rawResultRows} />
              <DataTable title="Raw Tables JSON Paths" rows={rawTablesRows} />
              <DataTable title="Raw Results JSON Paths" rows={rawResultsRows} />
              <DataTable title="Raw Road Summary JSON Paths" rows={rawRoadSummaryRows} />
              <DataTable title="Raw Roadway Submission JSON Paths" rows={rawRoadwaySubmissionRows} />
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Warnings</div>
              <div className="max-h-44 overflow-auto pr-1 text-xs text-muted">
                {(model?.warnings ?? []).length > 0 ? (
                  (model?.warnings ?? []).map((warning) => (
                    <div key={warning} className="mb-1 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                      {warning}
                    </div>
                  ))
                ) : (
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">No warnings surfaced.</div>
                )}
              </div>
            </section>
          </div>
        </div>
      }
      inspector={
        <InspectorPanel title="Inspector">
          <div className="space-y-3">
            <MetricCard label="Job Type" value={model?.jobType ?? "N/A"} />
            <MetricCard label="Backend" value={model ? `${model.backendName} (${model.solverVersion})` : "N/A"} />
            <MetricCard label="Source Dir" value={model?.sourceDir ?? "Not loaded"} />
            <MetricCard label="Known Runs" value={String(state.recentRuns.length)} />
            <MetricCard label="Loaded Jobs" value={String(state.projectJobs.length)} />
            <MetricCard label="Selected Table" value={state.selectedTableTitle || "N/A"} />
            <MetricCard label="Selected Row" value={state.selectedRowIndex >= 0 ? String(state.selectedRowIndex + 1) : "N/A"} />
            {state.selectedRow ? (
              <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                <div className="mb-1 text-text">Selected Row Data</div>
                <pre className="max-h-36 overflow-auto whitespace-pre-wrap">{JSON.stringify(state.selectedRow, null, 2)}</pre>
              </div>
            ) : null}
          </div>
        </InspectorPanel>
      }
      console={
        <ConsolePanel title="Console">
          <div className="space-y-1 text-xs text-muted">
            <div>Desktop contract: {state.contract?.contract_version ?? "unknown"}.</div>
            <div>Required files: {state.contract?.required_files.join(", ") ?? "result.json"}.</div>
            <div>Use `Load Latest Out` or Recent Runs to inspect backend outputs.</div>
          </div>
        </ConsolePanel>
      }
    />
  );
}
