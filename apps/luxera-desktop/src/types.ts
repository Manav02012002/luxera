import type { DesktopResultBundle, DesktopViewModel } from "./resultContracts";

export type JsonRow = Record<string, unknown>;

export interface RecentRun {
  resultDir: string;
  modifiedUnixS: number;
  jobId?: string | null;
  jobType?: string | null;
  contractVersion?: string | null;
}

export interface ArtifactRead {
  path: string;
  sizeBytes: number;
  truncated: boolean;
  content: string;
}

export interface ArtifactBinaryRead {
  path: string;
  sizeBytes: number;
  truncated: boolean;
  mimeType: string;
  dataBase64: string;
}

export interface ArtifactEntry {
  path: string;
  relativePath: string;
  sizeBytes: number;
  modifiedUnixS: number;
}

export interface BackendContract {
  contract_version: string;
  required_files: string[];
  optional_files: string[];
  rendered_sections: string[];
  max_read_artifact_bytes_default: number;
}

export interface ProjectJob {
  id: string;
  jobType: string;
  backend: string;
  seed: number;
}

export interface ProjectJobsResponse {
  projectPath: string;
  projectName?: string | null;
  jobs: ProjectJob[];
}

export interface ProjectDocument {
  path: string;
  name: string;
  schemaVersion: number;
  jobCount: number;
  content: string;
}

export interface ProjectValidationResult {
  valid: boolean;
  projectName?: string | null;
  schemaVersion?: number | null;
  checkedJobs: number;
  errors: string[];
  warnings: string[];
}

export interface GeometryOperationResult {
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  project?: ProjectDocument | null;
}

export interface ExportOperationResult {
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  outputPath: string;
}

export interface ToolOperationResult {
  success: boolean;
  message: string;
  data: Record<string, unknown> | null;
  project?: ProjectDocument | null;
}

export interface PhotometryVerifyResponse {
  ok: boolean;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

export interface FalseColorCell {
  lux: number;
  color: string;
}

export interface ContourPath {
  level: number;
  paths: number[][][];
}

export interface FalseColorGrid {
  name: string;
  origin: [number, number, number];
  width: number;
  height: number;
  nx: number;
  ny: number;
  elevation: number;
  cells: FalseColorCell[];
  stats: { min: number; max: number; avg: number; u0: number };
  contours: ContourPath[];
}

export interface FalseColorGridResponse {
  grids: FalseColorGrid[];
}

export interface BeamSpreadLuminaire {
  id: string;
  x: number;
  y: number;
  z: number;
  yaw_deg: number;
  beam_radius_c0: number;
  beam_radius_c90: number;
  field_radius_c0: number;
  field_radius_c90: number;
}

export interface BeamSpreadResponse {
  luminaires: BeamSpreadLuminaire[];
}

export interface StandardProfileOption {
  activity_type: string;
  description: string;
  maintained_illuminance_lux: number;
  uniformity_min: number;
  ugr_max: number;
  cri_min: number;
  standard_ref: string;
  category: string;
}

export interface QuickLayoutLuminaire {
  id: string;
  name: string;
  x: number;
  y: number;
  z: number;
  asset_id: string;
  yaw_deg?: number;
  maintenance_factor?: number;
  flux_multiplier?: number;
}

export interface QuickLayoutResult {
  best: {
    rows: number;
    cols: number;
    mean_lux: number;
    uniformity: number;
    fixture_count: number;
  };
  luminaires: QuickLayoutLuminaire[];
}

export interface JobRunResponse {
  projectPath: string;
  jobId: string;
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  resultDir?: string | null;
}

export interface JobRunStartResponse {
  runId: number;
  projectPath: string;
  jobId: string;
}

export interface JobRunPollResponse {
  runId: number;
  done: boolean;
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  resultDir?: string | null;
}

export type RunStatus = "idle" | "starting" | "running" | "completed" | "failed" | "cancelled";

export interface RunTimelineEvent {
  atUnixMs: number;
  status: RunStatus;
  message: string;
}

export interface RunHistoryEntry {
  localId: number;
  runId: number | null;
  projectPath: string;
  projectName: string;
  jobId: string;
  startedAtUnixMs: number;
  endedAtUnixMs: number | null;
  status: RunStatus;
  success: boolean | null;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  resultDir?: string | null;
}

export interface AgentRunEntry {
  atUnixMs: number;
  intent: string;
  approvalsJson: string;
  ok: boolean;
  actions: number;
  warnings: number;
  errors: number;
}

export interface AppState {
  resultDir: string;
  loading: boolean;
  error: string;
  bundle: DesktopResultBundle | null;
  model: DesktopViewModel | null;
  recentRuns: RecentRun[];
  recentLoading: boolean;
  recentProjects: string[];
  contract: BackendContract | null;
  projectPath: string;
  projectName: string;
  projectJobs: ProjectJob[];
  jobsLoading: boolean;
  selectedJobId: string;
  projectDoc: ProjectDocument | null;
  projectDocContent: string;
  projectDocDirty: boolean;
  projectValidation: ProjectValidationResult | null;
  projectLifecycleLoading: boolean;
  projectLifecycleError: string;
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
  gridName: string;
  gridWidth: string;
  gridHeight: string;
  gridElevation: string;
  gridNx: string;
  gridNy: string;
  gridOriginX: string;
  gridOriginY: string;
  gridOriginZ: string;
  workplanePreset: "floor" | "desk" | "standing" | "custom";
  standardProfiles: StandardProfileOption[];
  standardProfilesLoading: boolean;
  standardProfilesError: string;
  selectedStandardActivityType: string;
  selectedStandardProfileId: string;
  quickLayoutTargetLux: string;
  quickLayoutMaxRows: string;
  quickLayoutMaxCols: string;
  quickLayoutLoading: boolean;
  quickLayoutError: string;
  quickLayoutResult: QuickLayoutResult | null;
  quickLayoutPreviewEnabled: boolean;
  gridRoomId: string;
  jobIdInput: string;
  jobTypeInput: string;
  jobBackendInput: string;
  jobSeedInput: string;
  calcSetupLoading: boolean;
  calcSetupLogStdout: string;
  calcSetupLogStderr: string;
  calcSetupError: string;
  exportJobId: string;
  exportOutputPath: string;
  exportLoading: boolean;
  exportLogStdout: string;
  exportLogStderr: string;
  exportError: string;
  agentIntent: string;
  agentApprovalsJson: string;
  agentLoading: boolean;
  agentError: string;
  agentResponse: Record<string, unknown> | null;
  agentApprovalApplyDiff: boolean;
  agentApprovalRunJob: boolean;
  agentSelectedOptionIndex: string;
  agentRunHistory: AgentRunEntry[];
  materialIdInput: string;
  materialSurfaceIdsCsv: string;
  editRoomId: string;
  editRoomName: string;
  editRoomWidth: string;
  editRoomLength: string;
  editRoomHeight: string;
  editRoomOriginX: string;
  editRoomOriginY: string;
  editRoomOriginZ: string;
  apertureOpeningId: string;
  apertureVt: string;
  escapeRouteId: string;
  escapeRoutePolylineCsv: string;
  escapeRouteWidthM: string;
  escapeRouteSpacingM: string;
  escapeRouteHeightM: string;
  escapeRouteEndMarginM: string;
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
  variantIdInput: string;
  variantNameInput: string;
  variantDescriptionInput: string;
  variantDiffOpsJson: string;
  variantCompareJobId: string;
  variantCompareIdsCsv: string;
  variantCompareBaselineId: string;
  optimizationJobId: string;
  optimizationConstraintsJson: string;
  optimizationTopN: string;
  designLoading: boolean;
  designError: string;
  designMessage: string;
  designResult: Record<string, unknown> | null;
  falseColorData: FalseColorGridResponse | null;
  beamSpreadData: BeamSpreadResponse | null;
  falseColorOpacity: string;
  falseColorShowContours: boolean;
  falseColorShowValues: boolean;
  sceneZoom: number;
  scenePanX: number;
  scenePanY: number;
  sceneViewMode: "plan" | "3d";
  sceneCamYawDeg: string;
  sceneCamPitchDeg: string;
  sceneCamDistance: string;
  sceneCamTargetX: string;
  sceneCamTargetY: string;
  sceneCamTargetZ: string;
  placementMode: "none" | "grid" | "luminaire" | "room";
  layerRooms: boolean;
  layerSurfaces: boolean;
  layerOpenings: boolean;
  layerGrids: boolean;
  layerGridPoints: boolean;
  layerBeamSpread: boolean;
  layerFalseColor: boolean;
  layerLuminaires: boolean;
  layerTablePoints: boolean;
  sceneSelectActive: boolean;
  sceneSelectX0: number;
  sceneSelectY0: number;
  sceneSelectX1: number;
  sceneSelectY1: number;
  sceneSelectedLuminaireIdsCsv: string;
  gizmoMoveStepM: string;
  gizmoRotateStepDeg: string;
  gizmoSnapEnabled: boolean;
  gizmoMoveSnapM: string;
  gizmoAngleSnapDeg: string;
  gizmoAxisLock: "none" | "x" | "y";
  gizmoMoveFrame: "world" | "local";
  gizmoPreviewDx: number;
  gizmoPreviewDy: number;
  gizmoPreviewYawDeg: number;
  gizmoPreviewTarget: "none" | "luminaire" | "opening";
  inspectorLumTargetX: string;
  inspectorLumTargetY: string;
  inspectorLumTargetZ: string;
  inspectorLumTargetYaw: string;
  inspectorOpeningTargetX: string;
  inspectorOpeningTargetY: string;
  inspectorOpeningTargetZ: string;
  inspectorOpeningTargetYaw: string;
  selectedTableTitle: string;
  selectedRowIndex: number;
  selectedRow: JsonRow | null;
}
