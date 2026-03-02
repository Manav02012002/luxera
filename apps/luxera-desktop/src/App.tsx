import {
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
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
  AgentRunEntry,
  BackendContract,
  BeamSpreadResponse,
  DetailedComplianceResponse,
  ExportOperationResult,
  FalseColorGridResponse,
  GeometryOperationResult,
  JsonRow,
  LiveEstimateResult,
  PhotometryVerifyResponse,
  ProjectDocument,
  ProjectJobsResponse,
  ProjectValidationResult,
  QuickLayoutResult,
  RecentRun,
  StandardProfileOption,
  ToolOperationResult,
} from "./types";
import { flattenJsonRows, firstNumeric, objectToRows, rowsToPoints } from "./utils/table";
import { hasTauriRuntime, tauriDialogOpen, tauriDialogSave, tauriInvoke } from "./utils/tauri";

const projectItems = ["Project", "Geometry", "Luminaires", "Calculation", "Reports"];
const RECENT_PROJECTS_STORAGE_KEY = "luxera.desktop.recentProjects";
const MAX_RECENT_PROJECTS = 15;
const BEAM_WORKPLANE_Z = 0.8;

interface ScenePoint {
  id: string;
  x: number;
  y: number;
  z: number;
}

interface ScenePolygon {
  id: string;
  points: Array<{ x: number; y: number; z: number }>;
}

interface SceneGridPoint {
  x: number;
  y: number;
  z: number;
  color: string;
}

interface SceneGridPointSet {
  id: string;
  points: SceneGridPoint[];
  labelAnchor?: { x: number; y: number; z: number };
  labelText?: string;
}

interface LuminaireInstanceRow {
  id: string;
  name: string;
  assetId: string;
  x: number;
  y: number;
  z: number;
  yawDeg: number;
  maintenanceFactor: number;
  fluxMultiplier: number;
}

function fmt(value: number | undefined, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "N/A";
}

function fmtUnix(ts: number | undefined): string {
  if (typeof ts !== "number" || !Number.isFinite(ts) || ts <= 0) {
    return "N/A";
  }
  return new Date(ts * 1000).toLocaleString();
}

function pointsToSvgPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) {
    return "";
  }
  let out = `M ${points[0].x.toFixed(3)} ${points[0].y.toFixed(3)}`;
  for (let i = 1; i < points.length; i += 1) {
    out += ` L ${points[i].x.toFixed(3)} ${points[i].y.toFixed(3)}`;
  }
  return `${out} Z`;
}

function polarHalfToSvgPath(profile: Array<{ gammaDeg: number; candela: number }>, maxCandela: number, side: "right" | "left", cx: number, cy: number, radius: number): string {
  if (profile.length < 2 || !Number.isFinite(maxCandela) || maxCandela <= 1e-12) {
    return "";
  }
  const points = profile.map((p) => {
    const normalized = Math.max(0, p.candela) / maxCandela;
    const r = normalized * radius;
    // Photometric convention requested:
    // 0° at bottom (nadir), increasing clockwise.
    // Using SVG coordinates (y down), apply y inversion in projection.
    const svgAngleDeg = side === "right" ? p.gammaDeg - 90 : -p.gammaDeg - 90;
    const t = (svgAngleDeg * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(t),
      y: cy - r * Math.sin(t),
    };
  });
  let out = `M ${points[0].x.toFixed(3)} ${points[0].y.toFixed(3)}`;
  for (let i = 1; i < points.length; i += 1) {
    out += ` L ${points[i].x.toFixed(3)} ${points[i].y.toFixed(3)}`;
  }
  return out;
}

function beamEllipseWorldPoint(cx: number, cy: number, yawRad: number, radiusC0: number, radiusC90: number, thetaRad: number): { x: number; y: number } {
  const ct = Math.cos(thetaRad);
  const st = Math.sin(thetaRad);
  const cyaw = Math.cos(yawRad);
  const syaw = Math.sin(yawRad);
  return {
    x: cx + cyaw * radiusC0 * ct - syaw * radiusC90 * st,
    y: cy + syaw * radiusC0 * ct + cyaw * radiusC90 * st,
  };
}

const initialState: AppState = {
  resultDir: "",
  loading: false,
  error: "",
  bundle: null,
  model: null,
  complianceDetailed: null,
  complianceDetailedLoading: false,
  complianceDetailedError: "",
  recentRuns: [],
  recentLoading: false,
  recentProjects: [],
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
  gridName: "",
  gridWidth: "4",
  gridHeight: "4",
  gridElevation: "0.8",
  gridNx: "9",
  gridNy: "9",
  gridOriginX: "0",
  gridOriginY: "0",
  gridOriginZ: "0",
  workplanePreset: "custom",
  standardProfiles: [],
  standardProfilesLoading: false,
  standardProfilesError: "",
  selectedStandardActivityType: "",
  selectedStandardProfileId: "en12464_default",
  liveEstimate: null,
  liveEstimateLoading: false,
  liveEstimateError: "",
  quickLayoutTargetLux: "500",
  quickLayoutMaxRows: "6",
  quickLayoutMaxCols: "6",
  quickLayoutLoading: false,
  quickLayoutError: "",
  quickLayoutResult: null,
  quickLayoutPreviewEnabled: false,
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
  agentApprovalApplyDiff: false,
  agentApprovalRunJob: false,
  agentSelectedOptionIndex: "0",
  agentRunHistory: [],
  materialIdInput: "",
  materialSurfaceIdsCsv: "",
  editRoomId: "",
  editRoomName: "",
  editRoomWidth: "",
  editRoomLength: "",
  editRoomHeight: "",
  editRoomOriginX: "",
  editRoomOriginY: "",
  editRoomOriginZ: "",
  apertureOpeningId: "",
  apertureVt: "",
  escapeRouteId: "route_1",
  escapeRoutePolylineCsv: "0,0,0;3,0,0;3,4,0",
  escapeRouteWidthM: "1",
  escapeRouteSpacingM: "0.5",
  escapeRouteHeightM: "0",
  escapeRouteEndMarginM: "0",
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
  variantIdInput: "",
  variantNameInput: "",
  variantDescriptionInput: "",
  variantDiffOpsJson: "[]",
  variantCompareJobId: "",
  variantCompareIdsCsv: "",
  variantCompareBaselineId: "",
  optimizationJobId: "",
  optimizationConstraintsJson: "{}",
  optimizationTopN: "5",
  designLoading: false,
  designError: "",
  designMessage: "",
  designResult: null,
  falseColorData: null,
  beamSpreadData: null,
  falseColorOpacity: "0.7",
  falseColorShowContours: true,
  falseColorShowValues: false,
  sceneZoom: 1,
  scenePanX: 0,
  scenePanY: 0,
  sceneViewMode: "plan",
  sceneCamYawDeg: "38",
  sceneCamPitchDeg: "26",
  sceneCamDistance: "18",
  sceneCamTargetX: "0",
  sceneCamTargetY: "0",
  sceneCamTargetZ: "1.2",
  placementMode: "none",
  layerRooms: true,
  layerSurfaces: true,
  layerOpenings: true,
  layerGrids: true,
  layerGridPoints: true,
  layerBeamSpread: false,
  layerFalseColor: true,
  layerLuminaires: true,
  layerTablePoints: true,
  sceneSelectActive: false,
  sceneSelectX0: 0,
  sceneSelectY0: 0,
  sceneSelectX1: 0,
  sceneSelectY1: 0,
  sceneSelectedLuminaireIdsCsv: "",
  gizmoMoveStepM: "0.25",
  gizmoRotateStepDeg: "5",
  gizmoSnapEnabled: true,
  gizmoMoveSnapM: "0.05",
  gizmoAngleSnapDeg: "1",
  gizmoAxisLock: "none",
  gizmoMoveFrame: "world",
  gizmoPreviewDx: 0,
  gizmoPreviewDy: 0,
  gizmoPreviewYawDeg: 0,
  gizmoPreviewTarget: "none",
  inspectorLumTargetX: "",
  inspectorLumTargetY: "",
  inspectorLumTargetZ: "",
  inspectorLumTargetYaw: "",
  inspectorOpeningTargetX: "",
  inspectorOpeningTargetY: "",
  inspectorOpeningTargetZ: "",
  inspectorOpeningTargetYaw: "",
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
  const agentActionRows = useMemo<JsonRow[]>(
    () => (((state.agentResponse?.actions as unknown[]) ?? []).map((v, i) => (v && typeof v === "object" ? (v as JsonRow) : { index: i, value: String(v) }))),
    [state.agentResponse],
  );
  const agentDiffPreviewRows = useMemo<JsonRow[]>(
    () =>
      (((state.agentResponse?.diff_preview as unknown[]) ?? []).map((v, i) =>
        v && typeof v === "object" ? (v as JsonRow) : { index: i, value: String(v) },
      )),
    [state.agentResponse],
  );
  const agentWarningRows = useMemo<JsonRow[]>(
    () => (((state.agentResponse?.warnings as unknown[]) ?? []).map((v, i) => ({ index: i, warning: String(v) }))),
    [state.agentResponse],
  );
  const agentErrorRows = useMemo<JsonRow[]>(
    () => (((state.agentResponse?.errors as unknown[]) ?? []).map((v, i) => ({ index: i, error: String(v) }))),
    [state.agentResponse],
  );
  const agentHistoryRows = useMemo<JsonRow[]>(
    () =>
      state.agentRunHistory.map((r, i) => ({
        index: i + 1,
        at: new Date(r.atUnixMs).toLocaleString(),
        ok: r.ok,
        actions: r.actions,
        warnings: r.warnings,
        errors: r.errors,
        intent: r.intent,
      })),
    [state.agentRunHistory],
  );
  const designResultRows = useMemo(() => flattenJsonRows(state.designResult ?? null, "design"), [state.designResult]);
  const optimizationOptionsRows = useMemo<JsonRow[]>(
    () => ((state.designResult?.options as JsonRow[] | undefined) ?? []),
    [state.designResult],
  );
  const variantCompareRows = useMemo<JsonRow[]>(
    () => ((state.designResult?.rows as JsonRow[] | undefined) ?? []),
    [state.designResult],
  );
  const projectModel = useMemo<Record<string, unknown> | null>(() => {
    if (!state.projectDocContent.trim()) {
      return null;
    }
    try {
      const parsed = JSON.parse(state.projectDocContent) as Record<string, unknown>;
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  }, [state.projectDocContent]);
  const roomIds = useMemo<string[]>(
    () =>
      ((projectModel?.geometry as { rooms?: Array<{ id?: string }> } | undefined)?.rooms ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const surfaceIds = useMemo<string[]>(
    () =>
      ((projectModel?.geometry as { surfaces?: Array<{ id?: string }> } | undefined)?.surfaces ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const openingIds = useMemo<string[]>(
    () =>
      ((projectModel?.geometry as { openings?: Array<{ id?: string }> } | undefined)?.openings ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const luminaireIds = useMemo<string[]>(
    () =>
      ((projectModel?.luminaires as Array<{ id?: string }> | undefined) ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const materialIds = useMemo<string[]>(
    () =>
      ((projectModel?.materials as Array<{ id?: string }> | undefined) ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const assetIds = useMemo<string[]>(
    () =>
      ((projectModel?.photometry_assets as Array<{ id?: string }> | undefined) ?? [])
        .map((x) => String(x.id ?? ""))
        .filter((x) => x),
    [projectModel],
  );
  const selectedStandardProfile = useMemo<StandardProfileOption | null>(() => {
    const key = state.selectedStandardActivityType.trim();
    if (!key) {
      return null;
    }
    return state.standardProfiles.find((p) => p.activity_type === key) ?? null;
  }, [state.selectedStandardActivityType, state.standardProfiles]);
  const complianceTargetLux = useMemo<number | null>(() => {
    if (selectedStandardProfile && Number.isFinite(selectedStandardProfile.maintained_illuminance_lux)) {
      return Number(selectedStandardProfile.maintained_illuminance_lux);
    }
    const profiles = (projectModel?.compliance_profiles as Array<Record<string, unknown>> | undefined) ?? [];
    if (profiles.length === 0) {
      return null;
    }
    const thresholds = (profiles[0].thresholds as Record<string, unknown> | undefined) ?? {};
    const target = Number(thresholds.maintained_illuminance_lux ?? thresholds.target_lux ?? NaN);
    return Number.isFinite(target) ? target : null;
  }, [projectModel, selectedStandardProfile]);
  const standardProfilesByCategory = useMemo(() => {
    const map = new Map<string, StandardProfileOption[]>();
    for (const row of state.standardProfiles) {
      const category = row.category || "Other";
      if (!map.has(category)) {
        map.set(category, []);
      }
      map.get(category)?.push(row);
    }
    for (const [category, rows] of map.entries()) {
      rows.sort((a, b) => a.activity_type.localeCompare(b.activity_type));
      map.set(category, rows);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [state.standardProfiles]);
  const selectedLuminaireIdsSet = useMemo<Set<string>>(() => {
    const raw = state.sceneSelectedLuminaireIdsCsv
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v);
    if (raw.length > 0) {
      return new Set(raw);
    }
    const fallback = state.aimLuminaireId.trim();
    return fallback ? new Set([fallback]) : new Set<string>();
  }, [state.aimLuminaireId, state.sceneSelectedLuminaireIdsCsv]);
  const luminaireInstances = useMemo<LuminaireInstanceRow[]>(() => {
    const raw = (projectModel?.luminaires as Array<Record<string, unknown>> | undefined) ?? [];
    return raw
      .map((lum) => {
        const transform = (lum.transform as Record<string, unknown> | undefined) ?? {};
        const position = (transform.position as unknown[]) ?? [];
        const rotation = (transform.rotation as Record<string, unknown> | undefined) ?? {};
        const eulerDeg = (rotation.euler_deg as unknown[]) ?? [];
        const row: LuminaireInstanceRow = {
          id: String(lum.id ?? ""),
          name: String(lum.name ?? ""),
          assetId: String(lum.photometry_asset_id ?? ""),
          x: Number(position[0] ?? NaN),
          y: Number(position[1] ?? NaN),
          z: Number(position[2] ?? NaN),
          yawDeg: Number(eulerDeg[0] ?? 0),
          maintenanceFactor: Number(lum.maintenance_factor ?? 1),
          fluxMultiplier: Number(lum.flux_multiplier ?? 1),
        };
        return row;
      })
      .filter((row) => row.id && row.assetId && Number.isFinite(row.x) && Number.isFinite(row.y) && Number.isFinite(row.z));
  }, [projectModel]);
  const scheduleSummaryRows = useMemo<
    Array<{
      tag: string;
      quantity: number;
      avgMf: number;
      avgMultiplier: number;
      avgMountZ: number;
      luminaireIds: string[];
    }>
  >(() => {
    const groups = new Map<string, LuminaireInstanceRow[]>();
    for (const lum of luminaireInstances) {
      const key = lum.assetId;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)?.push(lum);
    }
    return Array.from(groups.entries())
      .map(([tag, lums]) => ({
        tag,
        quantity: lums.length,
        avgMf: lums.reduce((s, l) => s + l.maintenanceFactor, 0) / Math.max(lums.length, 1),
        avgMultiplier: lums.reduce((s, l) => s + l.fluxMultiplier, 0) / Math.max(lums.length, 1),
        avgMountZ: lums.reduce((s, l) => s + l.z, 0) / Math.max(lums.length, 1),
        luminaireIds: lums.map((l) => l.id),
      }))
      .sort((a, b) => a.tag.localeCompare(b.tag));
  }, [luminaireInstances]);
  const totalConnectedLoadWatts = useMemo<number | null>(() => {
    const assets = (projectModel?.photometry_assets as Array<Record<string, unknown>> | undefined) ?? [];
    const assetWatts = new Map<string, number>();
    const maybeNumber = (v: unknown): number | null => {
      const n = Number(v);
      return Number.isFinite(n) && n > 0 ? n : null;
    };
    for (const asset of assets) {
      const assetId = String(asset.id ?? "").trim();
      if (!assetId) {
        continue;
      }
      const metadata = (asset.metadata as Record<string, unknown> | undefined) ?? {};
      const candidates = [
        metadata.wattage,
        metadata.watts,
        metadata.lamp_watts,
        metadata.connected_watts,
        metadata.power_w,
      ];
      for (const candidate of candidates) {
        const n = maybeNumber(candidate);
        if (n !== null) {
          assetWatts.set(assetId, n);
          break;
        }
      }
    }
    let total = 0;
    let haveAny = false;
    for (const lum of luminaireInstances) {
      const watts = assetWatts.get(lum.assetId);
      if (watts === undefined) {
        continue;
      }
      haveAny = true;
      total += watts * (Number.isFinite(lum.fluxMultiplier) ? lum.fluxMultiplier : 1);
    }
    return haveAny ? total : null;
  }, [luminaireInstances, projectModel]);
  const selectedPhotometryAsset = useMemo<Record<string, unknown> | null>(() => {
    const assets = ((projectModel?.photometry_assets as Array<Record<string, unknown>> | undefined) ?? []) as Array<Record<string, unknown>>;
    const selectedId = state.selectedPhotometryAssetId.trim();
    if (!selectedId) {
      return null;
    }
    return assets.find((asset) => String(asset.id ?? "") === selectedId) ?? null;
  }, [projectModel, state.selectedPhotometryAssetId]);
  const projectPhotometryRows = useMemo<JsonRow[]>(
    () =>
      (((projectModel?.photometry_assets as Array<Record<string, unknown>> | undefined) ?? []).map((asset, i) => {
        const metadata = asset.metadata;
        const metaObj = metadata && typeof metadata === "object" ? (metadata as Record<string, unknown>) : null;
        return {
          index: i + 1,
          id: String(asset.id ?? ""),
          format: String(asset.format ?? ""),
          path: String(asset.path ?? ""),
          hash: String(asset.content_hash ?? ""),
          embedded: !!asset.embedded_b64,
          manufacturer: metaObj ? String(metaObj.manufacturer ?? "") : "",
          name: metaObj ? String(metaObj.name ?? "") : "",
        };
      })),
    [projectModel],
  );
  const filteredPhotometryRows = useMemo<JsonRow[]>(() => {
    const query = state.photometryLibraryQuery.trim().toLowerCase();
    if (!query) {
      return projectPhotometryRows;
    }
    return projectPhotometryRows.filter((row) =>
      Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(query)),
    );
  }, [projectPhotometryRows, state.photometryLibraryQuery]);
  const photometryVerifyRows = useMemo(() => flattenJsonRows(state.photometryVerifyResult ?? null, "photometry_verify"), [state.photometryVerifyResult]);
  const polarPlanes = useMemo(() => {
    const raw = (state.polarPlotData?.planes as unknown[]) ?? [];
    return raw
      .map((plane) => (plane && typeof plane === "object" ? (plane as Record<string, unknown>) : null))
      .filter((v): v is Record<string, unknown> => !!v);
  }, [state.polarPlotData]);
  const beamSpreadRows = useMemo(() => {
    const raw = (state.beamSpreadData?.luminaires as unknown[]) ?? [];
    return raw
      .map((entry) => (entry && typeof entry === "object" ? (entry as Record<string, unknown>) : null))
      .filter((entry): entry is Record<string, unknown> => !!entry)
      .map((entry) => ({
        id: String(entry.id ?? ""),
        x: Number(entry.x ?? NaN),
        y: Number(entry.y ?? NaN),
        z: Number(entry.z ?? NaN),
        yawDeg: Number(entry.yaw_deg ?? 0),
        beamRadiusC0: Number(entry.beam_radius_c0 ?? 0),
        beamRadiusC90: Number(entry.beam_radius_c90 ?? 0),
        fieldRadiusC0: Number(entry.field_radius_c0 ?? 0),
        fieldRadiusC90: Number(entry.field_radius_c90 ?? 0),
      }))
      .filter((entry) => Number.isFinite(entry.x) && Number.isFinite(entry.y) && Number.isFinite(entry.z));
  }, [state.beamSpreadData]);
  const quickLayoutPreviewLuminaires = useMemo(() => {
    if (!state.quickLayoutResult || !state.quickLayoutPreviewEnabled) {
      return [];
    }
    const rows = Array.isArray(state.quickLayoutResult.luminaires) ? state.quickLayoutResult.luminaires : [];
    return rows
      .map((row) => ({
        id: String(row.id ?? ""),
        x: Number(row.x ?? NaN),
        y: Number(row.y ?? NaN),
        z: Number(row.z ?? NaN),
      }))
      .filter((row) => row.id && Number.isFinite(row.x) && Number.isFinite(row.y) && Number.isFinite(row.z));
  }, [state.quickLayoutPreviewEnabled, state.quickLayoutResult]);
  const sceneRooms = useMemo<ScenePolygon[]>(() => {
    const rooms = ((projectModel?.geometry as { rooms?: Array<Record<string, unknown>> } | undefined)?.rooms ?? []) as Array<
      Record<string, unknown>
    >;
    const out: ScenePolygon[] = [];
    for (const room of rooms) {
      const id = String(room.id ?? "");
      if (!id) {
        continue;
      }
      const footprint = room.footprint as Array<[number, number]> | undefined;
      if (Array.isArray(footprint) && footprint.length >= 3) {
        const pts = footprint
          .map((v) => (Array.isArray(v) && v.length >= 2 ? { x: Number(v[0]), y: Number(v[1]), z: Number((room.origin as [number, number, number] | undefined)?.[2] ?? 0) } : null))
          .filter((v): v is { x: number; y: number; z: number } => !!v && Number.isFinite(v.x) && Number.isFinite(v.y) && Number.isFinite(v.z));
        if (pts.length >= 3) {
          out.push({ id, points: pts });
          continue;
        }
      }
      const origin = (room.origin as [number, number, number] | undefined) ?? [0, 0, 0];
      const x0 = Number(origin[0] ?? 0);
      const y0 = Number(origin[1] ?? 0);
      const w = Number(room.width ?? 0);
      const l = Number(room.length ?? 0);
      if (!Number.isFinite(x0) || !Number.isFinite(y0) || !Number.isFinite(w) || !Number.isFinite(l) || w <= 0 || l <= 0) {
        continue;
      }
      out.push({
        id,
        points: [
          { x: x0, y: y0, z: Number(origin[2] ?? 0) },
          { x: x0 + w, y: y0, z: Number(origin[2] ?? 0) },
          { x: x0 + w, y: y0 + l, z: Number(origin[2] ?? 0) },
          { x: x0, y: y0 + l, z: Number(origin[2] ?? 0) },
        ],
      });
    }
    return out;
  }, [projectModel]);
  const sceneSurfaces = useMemo<ScenePolygon[]>(() => {
    const surfaces = ((projectModel?.geometry as { surfaces?: Array<Record<string, unknown>> } | undefined)?.surfaces ?? []) as Array<
      Record<string, unknown>
    >;
    const out: ScenePolygon[] = [];
    for (const s of surfaces) {
      const id = String(s.id ?? "");
      const verts = (s.vertices as Array<[number, number, number]> | undefined) ?? [];
      const points = verts
        .map((v) => (Array.isArray(v) && v.length >= 3 ? { x: Number(v[0]), y: Number(v[1]), z: Number(v[2]) } : null))
        .filter((v): v is { x: number; y: number; z: number } => !!v && Number.isFinite(v.x) && Number.isFinite(v.y) && Number.isFinite(v.z));
      if (id && points.length >= 3) {
        out.push({ id, points });
      }
    }
    return out;
  }, [projectModel]);
  const sceneOpenings = useMemo<ScenePolygon[]>(() => {
    const openings = ((projectModel?.geometry as { openings?: Array<Record<string, unknown>> } | undefined)?.openings ?? []) as Array<
      Record<string, unknown>
    >;
    const out: ScenePolygon[] = [];
    for (const o of openings) {
      const id = String(o.id ?? "");
      const verts = (o.vertices as Array<[number, number, number]> | undefined) ?? [];
      const points = verts
        .map((v) => (Array.isArray(v) && v.length >= 3 ? { x: Number(v[0]), y: Number(v[1]), z: Number(v[2]) } : null))
        .filter((v): v is { x: number; y: number; z: number } => !!v && Number.isFinite(v.x) && Number.isFinite(v.y) && Number.isFinite(v.z));
      if (id && points.length >= 3) {
        out.push({ id, points });
      }
    }
    return out;
  }, [projectModel]);
  const sceneLuminaires = useMemo<ScenePoint[]>(() => {
    const lums = (projectModel?.luminaires as Array<Record<string, unknown>> | undefined) ?? [];
    const out: ScenePoint[] = [];
    for (const l of lums) {
      const id = String(l.id ?? "");
      const transform = l.transform as Record<string, unknown> | undefined;
      const pos = transform?.position as [number, number, number] | undefined;
      const x = Number((Array.isArray(pos) ? pos[0] : undefined) ?? NaN);
      const y = Number((Array.isArray(pos) ? pos[1] : undefined) ?? NaN);
      const z = Number((Array.isArray(pos) ? pos[2] : undefined) ?? NaN);
      if (id && Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
        out.push({ id, x, y, z });
      }
    }
    return out;
  }, [projectModel]);
  const sceneGrids = useMemo<ScenePolygon[]>(() => {
    const grids = (projectModel?.grids as Array<Record<string, unknown>> | undefined) ?? [];
    const out: ScenePolygon[] = [];
    for (const g of grids) {
      const id = String(g.id ?? "");
      const origin = (g.origin as [number, number, number] | undefined) ?? [0, 0, 0];
      const x0 = Number(origin[0] ?? 0);
      const y0 = Number(origin[1] ?? 0);
      const z0 = Number((origin[2] ?? 0) + Number(g.elevation ?? 0));
      const w = Number(g.width ?? 0);
      const h = Number(g.height ?? 0);
      if (id && Number.isFinite(x0) && Number.isFinite(y0) && Number.isFinite(z0) && Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
        out.push({
          id,
          points: [
            { x: x0, y: y0, z: z0 },
            { x: x0 + w, y: y0, z: z0 },
            { x: x0 + w, y: y0 + h, z: z0 },
            { x: x0, y: y0 + h, z: z0 },
          ],
        });
      }
    }
    return out;
  }, [projectModel]);
  const falseColorGridByName = useMemo(() => {
    const out = new Map<string, { cells: Array<{ color: string }> }>();
    const grids = state.falseColorData?.grids ?? [];
    for (const grid of grids) {
      const key = String(grid.name ?? "")
        .trim()
        .toLowerCase();
      if (key) {
        out.set(key, { cells: Array.isArray(grid.cells) ? grid.cells : [] });
      }
    }
    return out;
  }, [state.falseColorData]);
  const sceneGridPoints = useMemo<SceneGridPointSet[]>(() => {
    const grids = (projectModel?.grids as Array<Record<string, unknown>> | undefined) ?? [];
    const out: SceneGridPointSet[] = [];
    for (const g of grids) {
      const id = String(g.id ?? g.name ?? "").trim();
      const name = String(g.name ?? g.id ?? "").trim();
      if (!id && !name) {
        continue;
      }
      const origin = (g.origin as [number, number, number] | undefined) ?? [0, 0, 0];
      const x0 = Number(origin[0] ?? 0);
      const y0 = Number(origin[1] ?? 0);
      const z0 = Number((origin[2] ?? 0) + Number(g.elevation ?? 0));
      const width = Number(g.width ?? 0);
      const height = Number(g.height ?? 0);
      const nx = Math.max(1, Math.round(Number(g.nx ?? 1)));
      const ny = Math.max(1, Math.round(Number(g.ny ?? 1)));
      if (
        !Number.isFinite(x0) ||
        !Number.isFinite(y0) ||
        !Number.isFinite(z0) ||
        !Number.isFinite(width) ||
        !Number.isFinite(height) ||
        width <= 0 ||
        height <= 0
      ) {
        continue;
      }
      const count = nx * ny;
      const keyId = id.toLowerCase();
      const keyName = name.toLowerCase();
      const falseColor = falseColorGridByName.get(keyId) ?? falseColorGridByName.get(keyName);
      if (count > 400) {
        out.push({
          id: id || name,
          points: [],
          labelAnchor: { x: x0 + width * 0.5, y: y0 + height * 0.5, z: z0 },
          labelText: "400+ points",
        });
        continue;
      }
      const points: SceneGridPoint[] = [];
      const cellW = width / nx;
      const cellH = height / ny;
      for (let row = 0; row < ny; row += 1) {
        for (let col = 0; col < nx; col += 1) {
          const i = row * nx + col;
          const x = x0 + (col + 0.5) * cellW;
          const y = y0 + (row + 0.5) * cellH;
          const candidate = String(falseColor?.cells?.[i]?.color ?? "");
          const color = /^#[0-9A-Fa-f]{6}$/.test(candidate) ? candidate : "#4ade80";
          points.push({ x, y, z: z0, color });
        }
      }
      out.push({ id: id || name, points });
    }
    return out;
  }, [falseColorGridByName, projectModel]);
  const sceneGridPreview = useMemo<{
    outline: ScenePolygon | null;
    points: SceneGridPoint[];
    labelAnchor?: { x: number; y: number; z: number };
    labelText?: string;
  }>(() => {
    const required = [
      state.gridWidth,
      state.gridHeight,
      state.gridElevation,
      state.gridNx,
      state.gridNy,
      state.gridOriginX,
      state.gridOriginY,
    ];
    if (required.some((v) => !String(v ?? "").trim())) {
      return { outline: null, points: [] };
    }
    const width = Number(state.gridWidth);
    const height = Number(state.gridHeight);
    const elevation = Number(state.gridElevation);
    const nx = Math.max(1, Math.round(Number(state.gridNx)));
    const ny = Math.max(1, Math.round(Number(state.gridNy)));
    const ox = Number(state.gridOriginX);
    const oy = Number(state.gridOriginY);
    const oz = Number(state.gridOriginZ || "0");
    const z = oz + elevation;
    if (
      !Number.isFinite(width) ||
      !Number.isFinite(height) ||
      !Number.isFinite(elevation) ||
      !Number.isFinite(nx) ||
      !Number.isFinite(ny) ||
      !Number.isFinite(ox) ||
      !Number.isFinite(oy) ||
      !Number.isFinite(z) ||
      width <= 0 ||
      height <= 0
    ) {
      return { outline: null, points: [] };
    }
    const outline: ScenePolygon = {
      id: "__grid_preview__",
      points: [
        { x: ox, y: oy, z },
        { x: ox + width, y: oy, z },
        { x: ox + width, y: oy + height, z },
        { x: ox, y: oy + height, z },
      ],
    };
    const count = nx * ny;
    if (count > 400) {
      return {
        outline,
        points: [],
        labelAnchor: { x: ox + width * 0.5, y: oy + height * 0.5, z },
        labelText: "400+ points",
      };
    }
    const cellW = width / nx;
    const cellH = height / ny;
    const points: SceneGridPoint[] = [];
    for (let row = 0; row < ny; row += 1) {
      for (let col = 0; col < nx; col += 1) {
        points.push({
          x: ox + (col + 0.5) * cellW,
          y: oy + (row + 0.5) * cellH,
          z,
          color: "#86efac",
        });
      }
    }
    return { outline, points };
  }, [state.gridElevation, state.gridHeight, state.gridNx, state.gridNy, state.gridOriginX, state.gridOriginY, state.gridOriginZ, state.gridWidth]);
  const sceneBounds = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const p of sceneRooms) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
      }
    }
    for (const p of sceneSurfaces) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
      }
    }
    for (const p of sceneOpenings) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
      }
    }
    for (const p of sceneGrids) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
      }
    }
    for (const set of sceneGridPoints) {
      for (const p of set.points) {
        xs.push(p.x);
        ys.push(p.y);
      }
      if (set.labelAnchor) {
        xs.push(set.labelAnchor.x);
        ys.push(set.labelAnchor.y);
      }
    }
    if (sceneGridPreview.outline) {
      for (const v of sceneGridPreview.outline.points) {
        xs.push(v.x);
        ys.push(v.y);
      }
    }
    for (const p of sceneGridPreview.points) {
      xs.push(p.x);
      ys.push(p.y);
    }
    if (sceneGridPreview.labelAnchor) {
      xs.push(sceneGridPreview.labelAnchor.x);
      ys.push(sceneGridPreview.labelAnchor.y);
    }
    for (const p of sceneLuminaires) {
      xs.push(p.x);
      ys.push(p.y);
    }
    for (const p of quickLayoutPreviewLuminaires) {
      xs.push(p.x);
      ys.push(p.y);
    }
    for (const beam of beamSpreadRows) {
      const r = Math.max(beam.fieldRadiusC0, beam.fieldRadiusC90, beam.beamRadiusC0, beam.beamRadiusC90, 0);
      if (r > 0) {
        xs.push(beam.x - r, beam.x + r);
        ys.push(beam.y - r, beam.y + r);
      } else {
        xs.push(beam.x);
        ys.push(beam.y);
      }
    }
    if (xs.length === 0 || ys.length === 0) {
      return null;
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = Math.max(maxX - minX, 1e-6);
    const spanY = Math.max(maxY - minY, 1e-6);
    const padX = spanX * 0.06;
    const padY = spanY * 0.06;
    return {
      minX: minX - padX,
      maxX: maxX + padX,
      minY: minY - padY,
      maxY: maxY + padY,
    };
  }, [beamSpreadRows, quickLayoutPreviewLuminaires, sceneGridPoints, sceneGridPreview, sceneGrids, sceneLuminaires, sceneOpenings, sceneRooms, sceneSurfaces]);
  const sceneBounds3d = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    const zs: number[] = [];
    for (const p of sceneRooms) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
        zs.push(v.z);
      }
    }
    for (const p of sceneSurfaces) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
        zs.push(v.z);
      }
    }
    for (const p of sceneOpenings) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
        zs.push(v.z);
      }
    }
    for (const p of sceneGrids) {
      for (const v of p.points) {
        xs.push(v.x);
        ys.push(v.y);
        zs.push(v.z);
      }
    }
    for (const set of sceneGridPoints) {
      for (const p of set.points) {
        xs.push(p.x);
        ys.push(p.y);
        zs.push(p.z);
      }
      if (set.labelAnchor) {
        xs.push(set.labelAnchor.x);
        ys.push(set.labelAnchor.y);
        zs.push(set.labelAnchor.z);
      }
    }
    if (sceneGridPreview.outline) {
      for (const v of sceneGridPreview.outline.points) {
        xs.push(v.x);
        ys.push(v.y);
        zs.push(v.z);
      }
    }
    for (const p of sceneGridPreview.points) {
      xs.push(p.x);
      ys.push(p.y);
      zs.push(p.z);
    }
    if (sceneGridPreview.labelAnchor) {
      xs.push(sceneGridPreview.labelAnchor.x);
      ys.push(sceneGridPreview.labelAnchor.y);
      zs.push(sceneGridPreview.labelAnchor.z);
    }
    for (const p of sceneLuminaires) {
      xs.push(p.x);
      ys.push(p.y);
      zs.push(p.z);
    }
    for (const p of quickLayoutPreviewLuminaires) {
      xs.push(p.x);
      ys.push(p.y);
      zs.push(p.z);
    }
    for (const beam of beamSpreadRows) {
      const r = Math.max(beam.fieldRadiusC0, beam.fieldRadiusC90, beam.beamRadiusC0, beam.beamRadiusC90, 0);
      if (r > 0) {
        xs.push(beam.x - r, beam.x + r);
        ys.push(beam.y - r, beam.y + r);
      } else {
        xs.push(beam.x);
        ys.push(beam.y);
      }
      zs.push(BEAM_WORKPLANE_Z);
    }
    if (xs.length === 0 || ys.length === 0 || zs.length === 0) {
      return null;
    }
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
      minZ: Math.min(...zs),
      maxZ: Math.max(...zs),
    };
  }, [beamSpreadRows, quickLayoutPreviewLuminaires, sceneGridPoints, sceneGridPreview, sceneGrids, sceneLuminaires, sceneOpenings, sceneRooms, sceneSurfaces]);
  const selectedLuminaireRaw = useMemo(() => {
    const id = state.aimLuminaireId.trim();
    if (!id) {
      return null;
    }
    return sceneLuminaires.find((x) => x.id === id) ?? null;
  }, [sceneLuminaires, state.aimLuminaireId]);
  const selectedLuminairePoint = useMemo(() => {
    if (!selectedLuminaireRaw) {
      return null;
    }
    if (state.gizmoPreviewTarget !== "luminaire") {
      return selectedLuminaireRaw;
    }
    return {
      ...selectedLuminaireRaw,
      x: selectedLuminaireRaw.x + state.gizmoPreviewDx,
      y: selectedLuminaireRaw.y + state.gizmoPreviewDy,
    };
  }, [selectedLuminaireRaw, state.gizmoPreviewDx, state.gizmoPreviewDy, state.gizmoPreviewTarget]);
  const selectedLuminaireYawDeg = useMemo(() => {
    const id = state.aimLuminaireId.trim();
    if (!id) {
      return 0;
    }
    const lums = (projectModel?.luminaires as Array<Record<string, unknown>> | undefined) ?? [];
    const lum = lums.find((x) => String(x.id ?? "") === id);
    const rot = (lum?.transform as Record<string, unknown> | undefined)?.rotation as Record<string, unknown> | undefined;
    const euler = rot?.euler_deg as [number, number, number] | undefined;
    const yaw = Number(Array.isArray(euler) ? euler[0] : 0);
    return Number.isFinite(yaw) ? yaw : 0;
  }, [projectModel, state.aimLuminaireId]);
  const selectedLuminaireYawDisplayDeg = useMemo(
    () => (state.gizmoPreviewTarget === "luminaire" ? selectedLuminaireYawDeg + state.gizmoPreviewYawDeg : selectedLuminaireYawDeg),
    [selectedLuminaireYawDeg, state.gizmoPreviewTarget, state.gizmoPreviewYawDeg],
  );
  const selectedOpeningRawCenter = useMemo(() => {
    const id = state.apertureOpeningId.trim();
    if (!id) {
      return null;
    }
    const opening = sceneOpenings.find((x) => x.id === id);
    if (!opening || opening.points.length === 0) {
      return null;
    }
    const cx = opening.points.reduce((acc, v) => acc + v.x, 0) / opening.points.length;
    const cy = opening.points.reduce((acc, v) => acc + v.y, 0) / opening.points.length;
    const cz = opening.points.reduce((acc, v) => acc + v.z, 0) / opening.points.length;
    return { id, x: cx, y: cy, z: cz };
  }, [sceneOpenings, state.apertureOpeningId]);
  const selectedOpeningCenter = useMemo(() => {
    if (!selectedOpeningRawCenter) {
      return null;
    }
    if (state.gizmoPreviewTarget !== "opening") {
      return selectedOpeningRawCenter;
    }
    return {
      ...selectedOpeningRawCenter,
      x: selectedOpeningRawCenter.x + state.gizmoPreviewDx,
      y: selectedOpeningRawCenter.y + state.gizmoPreviewDy,
    };
  }, [selectedOpeningRawCenter, state.gizmoPreviewDx, state.gizmoPreviewDy, state.gizmoPreviewTarget]);
  const selectedOpeningYawDeg = useMemo(() => {
    const id = state.apertureOpeningId.trim();
    if (!id) {
      return 0;
    }
    const opening = sceneOpenings.find((x) => x.id === id);
    if (!opening || opening.points.length < 2) {
      return 0;
    }
    const a = opening.points[0];
    const b = opening.points[1];
    const yaw = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
    return Number.isFinite(yaw) ? yaw : 0;
  }, [sceneOpenings, state.apertureOpeningId]);
  const selectedOpeningYawDisplayDeg = useMemo(
    () => (state.gizmoPreviewTarget === "opening" ? selectedOpeningYawDeg + state.gizmoPreviewYawDeg : selectedOpeningYawDeg),
    [selectedOpeningYawDeg, state.gizmoPreviewTarget, state.gizmoPreviewYawDeg],
  );
  const undoDepth = useMemo(() => {
    const v = (projectModel?.assistant_undo_stack as unknown[]) ?? [];
    return Array.isArray(v) ? v.length : 0;
  }, [projectModel]);
  const redoDepth = useMemo(() => {
    const v = (projectModel?.assistant_redo_stack as unknown[]) ?? [];
    return Array.isArray(v) ? v.length : 0;
  }, [projectModel]);
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

  const loadComplianceDetailed = async (explicitResultDir?: string, explicitProjectPath?: string): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    const resultDir = (explicitResultDir ?? state.resultDir).trim();
    const projectPath = ((explicitProjectPath && explicitProjectPath.trim()) || state.projectPath || state.projectDoc?.path || "").trim();
    if (!resultDir) {
      patchState({ complianceDetailed: null, complianceDetailedLoading: false, complianceDetailedError: "" });
      return;
    }
    if (!projectPath) {
      patchState({
        complianceDetailed: null,
        complianceDetailedLoading: false,
        complianceDetailedError: "No compliance profile set. Select a standard in Calc Setup.",
      });
      return;
    }
    patchState({ complianceDetailedLoading: true, complianceDetailedError: "" });
    try {
      const payload = await tauriInvoke<DetailedComplianceResponse>("evaluate_compliance_detailed", {
        resultDir,
        projectPath,
      });
      patchState({ complianceDetailed: payload, complianceDetailedLoading: false, complianceDetailedError: "" });
    } catch (err) {
      patchState({
        complianceDetailed: null,
        complianceDetailedLoading: false,
        complianceDetailedError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const estimateDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const estimateIlluminanceFast = async (explicitProjectPath?: string): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    const projectPath = (explicitProjectPath ?? state.projectPath ?? state.projectDoc?.path ?? "").trim();
    if (!projectPath) {
      patchState({ liveEstimate: null, liveEstimateLoading: false, liveEstimateError: "" });
      return;
    }
    patchState({ liveEstimateLoading: true, liveEstimateError: "" });
    try {
      const payload = await tauriInvoke<LiveEstimateResult>("estimate_illuminance_fast", { projectPath });
      patchState({ liveEstimate: payload, liveEstimateLoading: false, liveEstimateError: "" });
    } catch (err) {
      patchState({
        liveEstimate: null,
        liveEstimateLoading: false,
        liveEstimateError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const scheduleLiveEstimateRefresh = (explicitProjectPath?: string): void => {
    if (!hasTauri) {
      return;
    }
    if (estimateDebounceRef.current) {
      clearTimeout(estimateDebounceRef.current);
    }
    estimateDebounceRef.current = setTimeout(() => {
      void estimateIlluminanceFast(explicitProjectPath);
    }, 300);
  };

  const loadFalseColorData = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ error: "Heatmap loading requires Tauri runtime." });
      return;
    }
    const resultDir = state.resultDir.trim();
    if (!resultDir) {
      patchState({ error: "Load a result directory before requesting heatmap data." });
      return;
    }
    try {
      const payload = await tauriInvoke<FalseColorGridResponse>("get_falsecolor_grid_data", {
        resultDir,
        gridName: null,
      });
      patchState({ falseColorData: payload, error: "" });
    } catch (err) {
      patchState({ error: err instanceof Error ? err.message : String(err) });
    }
  };

  const loadBeamSpreadData = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ error: "Beam spread loading requires Tauri runtime." });
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({ error: "Load or open a project before requesting beam spread data." });
      return;
    }
    try {
      const payload = await tauriInvoke<BeamSpreadResponse>("get_luminaire_beam_data", {
        projectPath,
      });
      patchState({ beamSpreadData: payload, error: "" });
    } catch (err) {
      patchState({ error: err instanceof Error ? err.message : String(err) });
    }
  };

  const loadStandardProfiles = async (): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    patchState({ standardProfilesLoading: true, standardProfilesError: "" });
    try {
      const payload = await tauriInvoke<StandardProfileOption[]>("list_standard_profiles", {});
      const rows = Array.isArray(payload) ? payload : [];
      patchState({
        standardProfilesLoading: false,
        standardProfiles: rows,
        selectedStandardActivityType: state.selectedStandardActivityType || (rows.length > 0 ? String(rows[0].activity_type ?? "") : ""),
        standardProfilesError: "",
      });
    } catch (err) {
      patchState({
        standardProfilesLoading: false,
        standardProfilesError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyStandardProfile = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ calcSetupError: "Standard profile apply requires Tauri runtime." });
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({ calcSetupError: "Open a project before applying a standard profile." });
      return;
    }
    const selected = selectedStandardProfile;
    if (!selected) {
      patchState({ calcSetupError: "Select a standard profile first." });
      return;
    }
    const profileId = state.selectedStandardProfileId.trim() || `en12464_${selected.activity_type.toLowerCase()}`;
    const thresholds = {
      maintained_illuminance_lux: selected.maintained_illuminance_lux,
      uniformity_min: selected.uniformity_min,
      ugr_max: selected.ugr_max,
      cri_min: selected.cri_min,
    };
    patchState({ calcSetupLoading: true, calcSetupError: "", calcSetupLogStdout: "", calcSetupLogStderr: "" });
    try {
      const res = await tauriInvoke<ToolOperationResult>("set_compliance_profile_in_project", {
        projectPath,
        profileId,
        activityType: selected.activity_type,
        thresholdsJson: JSON.stringify(thresholds),
      });
      if (res.project) {
        patchState({
          projectDoc: res.project,
          projectDocContent: res.project.content,
          projectDocDirty: false,
          projectPath: res.project.path,
          projectName: res.project.name,
        });
        await loadProjectJobs(res.project.path);
      }
      patchState({
        calcSetupLoading: false,
        calcSetupLogStdout: res.message || "Compliance profile applied.",
        calcSetupLogStderr: res.success ? "" : JSON.stringify(res.data ?? {}, null, 2),
        calcSetupError: res.success ? "" : res.message || "Failed to apply compliance profile.",
      });
    } catch (err) {
      patchState({
        calcSetupLoading: false,
        calcSetupError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyWorkplanePreset = (value: "floor" | "desk" | "standing" | "custom"): void => {
    if (value === "floor") {
      patchState({ workplanePreset: value, gridElevation: "0.0" });
      return;
    }
    if (value === "desk") {
      patchState({ workplanePreset: value, gridElevation: "0.75" });
      return;
    }
    if (value === "standing") {
      patchState({ workplanePreset: value, gridElevation: "1.2" });
      return;
    }
    patchState({ workplanePreset: "custom" });
  };

  const startGridPlacement = (): void => {
    if (state.sceneViewMode !== "plan") {
      patchState({ calcSetupError: "Switch to plan view for click-to-place." });
      return;
    }
    placementRef.current.phase = "idle";
    placementRef.current.pointerId = null;
    patchState({ placementMode: "grid", calcSetupError: "" });
  };

  const proposeQuickLayout = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ quickLayoutError: "Quick layout requires Tauri runtime." });
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({ quickLayoutError: "Open a project before running quick layout." });
      return;
    }
    const targetLux = Number(state.quickLayoutTargetLux);
    const maxRows = Number(state.quickLayoutMaxRows);
    const maxCols = Number(state.quickLayoutMaxCols);
    if (!Number.isFinite(targetLux) || targetLux <= 0 || !Number.isFinite(maxRows) || maxRows < 1 || !Number.isFinite(maxCols) || maxCols < 1) {
      patchState({ quickLayoutError: "Quick layout inputs are invalid." });
      return;
    }
    patchState({ quickLayoutLoading: true, quickLayoutError: "", quickLayoutResult: null });
    try {
      const payload = await tauriInvoke<QuickLayoutResult>("propose_quick_layout", {
        projectPath,
        targetLux,
        maxRows: Math.round(maxRows),
        maxCols: Math.round(maxCols),
      });
      patchState({
        quickLayoutLoading: false,
        quickLayoutResult: payload,
        quickLayoutError: "",
        quickLayoutPreviewEnabled: true,
      });
    } catch (err) {
      patchState({
        quickLayoutLoading: false,
        quickLayoutError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const applyQuickLayout = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ quickLayoutError: "Quick layout apply requires Tauri runtime." });
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({ quickLayoutError: "Open a project before applying quick layout." });
      return;
    }
    const result = state.quickLayoutResult;
    if (!result || !Array.isArray(result.luminaires) || result.luminaires.length === 0) {
      patchState({ quickLayoutError: "Run Calculate Layout first." });
      return;
    }
    patchState({ quickLayoutLoading: true, quickLayoutError: "" });
    try {
      const res = await tauriInvoke<ToolOperationResult>("apply_quick_layout", {
        projectPath,
        luminairesJson: JSON.stringify(result.luminaires),
      });
      if (res.project) {
        patchState({
          projectDoc: res.project,
          projectDocContent: res.project.content,
          projectDocDirty: false,
          projectPath: res.project.path,
          projectName: res.project.name,
        });
        await loadProjectJobs(res.project.path);
      }
      patchState({
        quickLayoutLoading: false,
        quickLayoutPreviewEnabled: false,
        quickLayoutError: res.success ? "" : (res.message || "Quick layout apply failed."),
      });
    } catch (err) {
      patchState({
        quickLayoutLoading: false,
        quickLayoutError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const persistRecentProjects = async (paths: string[]): Promise<void> => {
    if (hasTauri) {
      try {
        await tauriInvoke<boolean>("save_recent_projects_store", { projects: paths });
        return;
      } catch {
        // Fallback to localStorage in web/dev mode.
      }
    }
    try {
      window.localStorage.setItem(RECENT_PROJECTS_STORAGE_KEY, JSON.stringify(paths));
    } catch {
      // Best effort only.
    }
  };

  const pushRecentProjectPath = (projectPath: string): void => {
    const normalized = projectPath.trim();
    if (!normalized) {
      return;
    }
    const next = [normalized, ...state.recentProjects.filter((p) => p !== normalized)].slice(0, MAX_RECENT_PROJECTS);
    patchState({ recentProjects: next });
    void persistRecentProjects(next);
  };

  const browseProjectPath = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Open Luxera Project",
        defaultPath: state.projectPath.trim() || undefined,
        multiple: false,
        directory: false,
        filters: [{ name: "Project JSON", extensions: ["json"] }],
      });
      if (typeof picked === "string" && picked.trim()) {
        patchState({ projectPath: picked, projectLifecycleError: "" });
      }
    } catch (err) {
      patchState({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const openProjectFromDialog = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Open Luxera Project",
        defaultPath: state.projectPath.trim() || undefined,
        multiple: false,
        directory: false,
        filters: [{ name: "Project JSON", extensions: ["json"] }],
      });
      if (typeof picked === "string" && picked.trim()) {
        await openProjectDocument(picked);
      }
    } catch (err) {
      patchState({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const chooseNewProjectPathAndInit = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogSave({
        title: "Create New Luxera Project",
        defaultPath: state.projectPath.trim() || undefined,
      });
      if (typeof picked === "string" && picked.trim()) {
        await initProjectDocument(picked);
      }
    } catch (err) {
      patchState({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const saveProjectAsDialog = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogSave({
        title: "Save Luxera Project As",
        defaultPath: state.projectPath.trim() || undefined,
      });
      if (typeof picked === "string" && picked.trim()) {
        await saveProjectDocument(picked);
      }
    } catch (err) {
      patchState({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const browseGeometryImportPath = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ geomError: "Geometry browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Import Geometry",
        defaultPath: state.geomImportPath.trim() || undefined,
        multiple: false,
        directory: false,
        filters: [
          { name: "Geometry Files", extensions: ["dxf", "obj", "gltf", "glb", "fbx", "skp", "ifc", "dwg"] },
          { name: "All Files", extensions: ["*"] },
        ],
      });
      if (typeof picked === "string" && picked.trim()) {
        patchState({ geomImportPath: picked, geomError: "" });
      }
    } catch (err) {
      patchState({ geomError: err instanceof Error ? err.message : String(err) });
    }
  };

  const browsePhotometryPath = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ luminaireError: "Photometry browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Import Photometry",
        defaultPath: state.photometryFilePath.trim() || undefined,
        multiple: false,
        directory: false,
        filters: [
          { name: "Photometry", extensions: ["ies", "ldt"] },
          { name: "All Files", extensions: ["*"] },
        ],
      });
      if (typeof picked === "string" && picked.trim()) {
        patchState({ photometryFilePath: picked, luminaireError: "" });
      }
    } catch (err) {
      patchState({ luminaireError: err instanceof Error ? err.message : String(err) });
    }
  };

  const browseExportOutputPath = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ exportError: "Export path browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogSave({
        title: "Choose Export Output Path",
        defaultPath: state.exportOutputPath.trim() || undefined,
      });
      if (typeof picked === "string" && picked.trim()) {
        patchState({ exportOutputPath: picked, exportError: "" });
      }
    } catch (err) {
      patchState({ exportError: err instanceof Error ? err.message : String(err) });
    }
  };

  const loadProjectJobs = async (pathOverride?: string): Promise<void> => {
    if (!hasTauri) {
      // surfaced in run control panel
      return;
    }
    const path = (pathOverride ?? state.projectPath).trim();
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
      pushRecentProjectPath(doc.path);
      await loadProjectJobs(doc.path);
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const initProjectDocument = async (pathOverride?: string): Promise<void> => {
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
      pushRecentProjectPath(doc.path);
      await loadProjectJobs(doc.path);
    } catch (err) {
      patchState({
        projectLifecycleLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const saveProjectDocument = async (pathOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patchState({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (pathOverride ?? state.projectPath).trim();
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
      pushRecentProjectPath(doc.path);
      await loadProjectJobs(doc.path);
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
      if (res.success) {
        scheduleLiveEstimateRefresh(res.project.path);
      }
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
      if (res.success) {
        scheduleLiveEstimateRefresh(res.project.path);
      }
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

  const verifyImportPhotometry = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ photometryVerifyError: "Photometry verification requires Tauri runtime." });
      return;
    }
    const path = state.photometryFilePath.trim();
    if (!path) {
      patchState({ photometryVerifyError: "Photometry file path is empty.", photometryVerifyResult: null });
      return;
    }
    patchState({ photometryVerifyLoading: true, photometryVerifyError: "", photometryVerifyResult: null });
    try {
      const res = await tauriInvoke<PhotometryVerifyResponse>("verify_photometry_file_input", {
        filePath: path,
        format: state.photometryFormat.trim() ? state.photometryFormat.trim() : null,
      });
      patchState({
        photometryVerifyLoading: false,
        photometryVerifyError: res.ok ? "" : String(res.error ?? "Photometry verification failed."),
        photometryVerifyResult: res.result ?? null,
      });
    } catch (err) {
      patchState({
        photometryVerifyLoading: false,
        photometryVerifyError: err instanceof Error ? err.message : String(err),
        photometryVerifyResult: null,
      });
    }
  };

  const verifySelectedProjectPhotometry = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ photometryVerifyError: "Photometry verification requires Tauri runtime." });
      return;
    }
    const projectPath = state.projectPath.trim();
    const assetId = state.selectedPhotometryAssetId.trim();
    if (!projectPath) {
      patchState({ photometryVerifyError: "Project path is empty.", photometryVerifyResult: null });
      return;
    }
    if (!assetId) {
      patchState({ photometryVerifyError: "Select a photometry asset first.", photometryVerifyResult: null });
      return;
    }
    patchState({ photometryVerifyLoading: true, photometryVerifyError: "", photometryVerifyResult: null });
    try {
      const res = await tauriInvoke<PhotometryVerifyResponse>("verify_project_photometry_asset", {
        projectPath,
        assetId,
      });
      patchState({
        photometryVerifyLoading: false,
        photometryVerifyError: res.ok ? "" : String(res.error ?? "Photometry verification failed."),
        photometryVerifyResult: res.result ?? null,
      });
    } catch (err) {
      patchState({
        photometryVerifyLoading: false,
        photometryVerifyError: err instanceof Error ? err.message : String(err),
        photometryVerifyResult: null,
      });
    }
  };

  const loadPolarDistribution = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ polarPlotError: "Polar distribution requires Tauri runtime.", polarPlotData: null });
      return;
    }
    const asset = selectedPhotometryAsset;
    const filePath = String(asset?.path ?? state.photometryFilePath).trim();
    const format = String(asset?.format ?? state.photometryFormat).trim();
    if (!filePath) {
      patchState({ polarPlotError: "Selected photometry asset has no file path.", polarPlotData: null });
      return;
    }
    patchState({ polarPlotLoading: true, polarPlotError: "", polarPlotData: null });
    try {
      const payload = await tauriInvoke<Record<string, unknown>>("get_photometry_polar_data", {
        filePath,
        format: format ? format : null,
      });
      patchState({ polarPlotLoading: false, polarPlotData: payload, polarPlotError: "" });
    } catch (err) {
      patchState({
        polarPlotLoading: false,
        polarPlotData: null,
        polarPlotError: err instanceof Error ? err.message : String(err),
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
    let approvalsObj: Record<string, unknown> = {};
    if (state.agentApprovalsJson.trim()) {
      try {
        const parsed = JSON.parse(state.agentApprovalsJson) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          approvalsObj = parsed as Record<string, unknown>;
        } else {
          patchState({ agentError: "Approvals JSON must be an object." });
          return;
        }
      } catch (err) {
        patchState({ agentError: err instanceof Error ? `Invalid approvals JSON: ${err.message}` : "Invalid approvals JSON." });
        return;
      }
    }
    approvalsObj.apply_diff = state.agentApprovalApplyDiff;
    approvalsObj.run_job = state.agentApprovalRunJob;
    const selectedIdx = Number(state.agentSelectedOptionIndex);
    if (Number.isFinite(selectedIdx) && selectedIdx >= 0) {
      approvalsObj.selected_option_index = Math.round(selectedIdx);
    }
    const approvalsJson = JSON.stringify(approvalsObj);
    patchState({ agentLoading: true, agentError: "", agentResponse: null });
    try {
      const payload = await tauriInvoke<{ response: Record<string, unknown> }>("execute_agent_intent", {
        projectPath: state.projectPath,
        intent: state.agentIntent,
        approvalsJson,
      });
      const warnings = ((payload.response.warnings as unknown[]) ?? []).length;
      const errors = ((payload.response.errors as unknown[]) ?? []).length;
      const actions = ((payload.response.actions as unknown[]) ?? []).length;
      const ok = errors === 0;
      const historyEntry: AgentRunEntry = {
        atUnixMs: Date.now(),
        intent: state.agentIntent,
        approvalsJson,
        ok,
        actions,
        warnings,
        errors,
      };
      patchState({
        agentLoading: false,
        agentApprovalsJson: approvalsJson,
        agentResponse: payload.response,
        agentRunHistory: [historyEntry, ...state.agentRunHistory].slice(0, 25),
      });
      await openProjectDocument(state.projectPath);
    } catch (err) {
      patchState({
        agentLoading: false,
        agentError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const batchUpdateSelectedLuminaires = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Batch luminaire operations require Tauri runtime." });
      return;
    }
    const idsCsv = state.sceneSelectedLuminaireIdsCsv.trim() || state.aimLuminaireId.trim();
    if (!idsCsv) {
      patchState({ designError: "No luminaires selected for batch update." });
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
      patchState({ designError: "Batch luminaire numeric values are invalid." });
      return;
    }
    if (yaw === null && maintenance === null && flux === null && tilt === null) {
      patchState({ designError: "Provide at least one batch luminaire field to update." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("batch_update_luminaires_in_project", {
        projectPath: state.projectPath,
        luminaireIdsCsv: idsCsv,
        yawDeg: yaw,
        maintenanceFactor: maintenance,
        fluxMultiplier: flux,
        tiltDeg: tilt,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const nudgeLuminaireGizmo = async (dx: number, dy: number, dz: number, dyawDeg: number): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Luminaire gizmo requires Tauri runtime." });
      return;
    }
    const luminaireId = state.aimLuminaireId.trim();
    if (!luminaireId) {
      patchState({ designError: "Select a luminaire to move/rotate." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("nudge_luminaire_in_project", {
        projectPath: state.projectPath,
        luminaireId,
        deltaX: dx,
        deltaY: dy,
        deltaZ: dz,
        deltaYawDeg: dyawDeg,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const transformOpeningGizmo = async (dx: number, dy: number, dz: number, dyawDeg: number): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Opening gizmo requires Tauri runtime." });
      return;
    }
    const openingId = state.apertureOpeningId.trim();
    if (!openingId) {
      patchState({ designError: "Select an opening to move/rotate." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("transform_opening_in_project", {
        projectPath: state.projectPath,
        openingId,
        deltaX: dx,
        deltaY: dy,
        deltaZ: dz,
        deltaYawDeg: dyawDeg,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applyLuminaireInspectorAbsolute = async (): Promise<void> => {
    if (!selectedLuminaireRaw) {
      patchState({ designError: "Select a luminaire first." });
      return;
    }
    const tx = Number(state.inspectorLumTargetX);
    const ty = Number(state.inspectorLumTargetY);
    const tz = Number(state.inspectorLumTargetZ);
    const tyaw = Number(state.inspectorLumTargetYaw);
    if (![tx, ty, tz, tyaw].every(Number.isFinite)) {
      patchState({ designError: "Luminaire inspector values are invalid." });
      return;
    }
    const dx = tx - selectedLuminaireRaw.x;
    const dy = ty - selectedLuminaireRaw.y;
    const dz = tz - selectedLuminaireRaw.z;
    const dyaw = tyaw - selectedLuminaireYawDeg;
    await nudgeLuminaireGizmo(dx, dy, dz, dyaw);
  };

  const applyOpeningInspectorAbsolute = async (): Promise<void> => {
    if (!selectedOpeningRawCenter) {
      patchState({ designError: "Select an opening first." });
      return;
    }
    const tx = Number(state.inspectorOpeningTargetX);
    const ty = Number(state.inspectorOpeningTargetY);
    const tz = Number(state.inspectorOpeningTargetZ);
    const tyaw = Number(state.inspectorOpeningTargetYaw);
    if (![tx, ty, tz, tyaw].every(Number.isFinite)) {
      patchState({ designError: "Opening inspector values are invalid." });
      return;
    }
    const dx = tx - selectedOpeningRawCenter.x;
    const dy = ty - selectedOpeningRawCenter.y;
    const dz = tz - selectedOpeningRawCenter.z;
    const dyaw = tyaw - selectedOpeningYawDeg;
    await transformOpeningGizmo(dx, dy, dz, dyaw);
  };

  const undoProjectChange = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Undo requires Tauri runtime." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("undo_project_change", {
        projectPath: state.projectPath,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const redoProjectChange = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Redo requires Tauri runtime." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("redo_project_change", {
        projectPath: state.projectPath,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applyDesignResult = async (res: ToolOperationResult, refreshProject: boolean): Promise<void> => {
    patchState({
      designLoading: false,
      designError: res.success ? "" : res.message || "Operation failed.",
      designMessage: res.message,
      designResult: (res.data as Record<string, unknown> | null) ?? null,
    });
    if (refreshProject && res.success && res.project) {
      patchState({
        projectDoc: res.project,
        projectDocContent: res.project.content,
        projectDocDirty: false,
        projectPath: res.project.path,
        projectName: res.project.name,
      });
      await loadProjectJobs();
      scheduleLiveEstimateRefresh(res.project.path);
    }
  };

  const assignMaterial = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Design authoring requires Tauri runtime." });
      return;
    }
    if (!state.materialIdInput.trim()) {
      patchState({ designError: "Material id is required." });
      return;
    }
    if (!state.materialSurfaceIdsCsv.trim()) {
      patchState({ designError: "At least one surface id is required." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("assign_material_in_project", {
        projectPath: state.projectPath,
        materialId: state.materialIdInput.trim(),
        surfaceIdsCsv: state.materialSurfaceIdsCsv.trim(),
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const editRoom = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Room editing requires Tauri runtime." });
      return;
    }
    if (!state.editRoomId.trim()) {
      patchState({ designError: "Edit room id is required." });
      return;
    }
    const parseOptional = (value: string): number | null => {
      if (!value.trim()) {
        return null;
      }
      const n = Number(value);
      return Number.isFinite(n) ? n : Number.NaN;
    };
    const width = parseOptional(state.editRoomWidth);
    const length = parseOptional(state.editRoomLength);
    const height = parseOptional(state.editRoomHeight);
    const ox = parseOptional(state.editRoomOriginX);
    const oy = parseOptional(state.editRoomOriginY);
    const oz = parseOptional(state.editRoomOriginZ);
    if ([width, length, height, ox, oy, oz].some((v) => typeof v === "number" && Number.isNaN(v))) {
      patchState({ designError: "Edit room numeric fields are invalid." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("edit_room_in_project", {
        projectPath: state.projectPath,
        roomId: state.editRoomId.trim(),
        name: state.editRoomName.trim() ? state.editRoomName.trim() : null,
        width,
        length,
        height,
        originX: ox,
        originY: oy,
        originZ: oz,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const setDaylightAperture = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Aperture editing requires Tauri runtime." });
      return;
    }
    if (!state.apertureOpeningId.trim()) {
      patchState({ designError: "Opening id is required." });
      return;
    }
    const vt = state.apertureVt.trim() ? Number(state.apertureVt) : null;
    if (vt !== null && !Number.isFinite(vt)) {
      patchState({ designError: "Visible transmittance is invalid." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("set_daylight_aperture_in_project", {
        projectPath: state.projectPath,
        openingId: state.apertureOpeningId.trim(),
        visibleTransmittance: vt,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const addEscapeRoute = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Escape route authoring requires Tauri runtime." });
      return;
    }
    if (!state.escapeRouteId.trim()) {
      patchState({ designError: "Escape route id is required." });
      return;
    }
    if (!state.escapeRoutePolylineCsv.trim()) {
      patchState({ designError: "Escape route polyline is required." });
      return;
    }
    const widthM = Number(state.escapeRouteWidthM);
    const spacingM = Number(state.escapeRouteSpacingM);
    const heightM = Number(state.escapeRouteHeightM);
    const endMarginM = Number(state.escapeRouteEndMarginM);
    if (![widthM, spacingM, heightM, endMarginM].every(Number.isFinite)) {
      patchState({ designError: "Escape route numeric fields are invalid." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("add_escape_route_in_project", {
        projectPath: state.projectPath,
        routeId: state.escapeRouteId.trim(),
        polylineCsv: state.escapeRoutePolylineCsv.trim(),
        widthM,
        spacingM,
        heightM,
        endMarginM,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const arrayLuminaires = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Luminaire arrays require Tauri runtime." });
      return;
    }
    if (!state.arrayRoomId.trim() || !state.arrayAssetId.trim()) {
      patchState({ designError: "Array room id and asset id are required." });
      return;
    }
    const rows = Number(state.arrayRows);
    const cols = Number(state.arrayCols);
    const marginM = Number(state.arrayMarginM);
    const mountHeightM = Number(state.arrayMountHeightM);
    if (![rows, cols, marginM, mountHeightM].every(Number.isFinite) || rows < 1 || cols < 1) {
      patchState({ designError: "Luminaire array inputs are invalid." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("array_luminaires_in_project", {
        projectPath: state.projectPath,
        roomId: state.arrayRoomId.trim(),
        assetId: state.arrayAssetId.trim(),
        rows: Math.round(rows),
        cols: Math.round(cols),
        marginM,
        mountHeightM,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const aimLuminaire = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Luminaire aiming requires Tauri runtime." });
      return;
    }
    if (!state.aimLuminaireId.trim()) {
      patchState({ designError: "Luminaire id is required for aiming." });
      return;
    }
    const yawDeg = Number(state.aimYawDeg);
    if (!Number.isFinite(yawDeg)) {
      patchState({ designError: "Yaw degrees is invalid." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("aim_luminaire_in_project", {
        projectPath: state.projectPath,
        luminaireId: state.aimLuminaireId.trim(),
        yawDeg,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const addVariant = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Variants require Tauri runtime." });
      return;
    }
    if (!state.variantIdInput.trim() || !state.variantNameInput.trim()) {
      patchState({ designError: "Variant id and name are required." });
      return;
    }
    if (state.variantDiffOpsJson.trim()) {
      try {
        const parsed = JSON.parse(state.variantDiffOpsJson);
        if (!Array.isArray(parsed)) {
          patchState({ designError: "Variant diff JSON must be an array." });
          return;
        }
      } catch (err) {
        patchState({ designError: err instanceof Error ? `Invalid variant diff JSON: ${err.message}` : "Invalid variant diff JSON." });
        return;
      }
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("add_project_variant", {
        projectPath: state.projectPath,
        variantId: state.variantIdInput.trim(),
        name: state.variantNameInput.trim(),
        description: state.variantDescriptionInput.trim() ? state.variantDescriptionInput.trim() : null,
        diffOpsJson: state.variantDiffOpsJson.trim() ? state.variantDiffOpsJson.trim() : "[]",
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const compareVariants = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Variant comparison requires Tauri runtime." });
      return;
    }
    const jobId = (state.variantCompareJobId || state.selectedJobId).trim();
    if (!jobId) {
      patchState({ designError: "Variant compare job id is required." });
      return;
    }
    if (!state.variantCompareIdsCsv.trim()) {
      patchState({ designError: "Variant ids CSV is required." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("compare_project_variants", {
        projectPath: state.projectPath,
        jobId,
        variantIdsCsv: state.variantCompareIdsCsv.trim(),
        baselineVariantId: state.variantCompareBaselineId.trim() ? state.variantCompareBaselineId.trim() : null,
      });
      await applyDesignResult(res, false);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const proposeOptimizations = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Optimization requires Tauri runtime." });
      return;
    }
    const jobId = (state.optimizationJobId || state.selectedJobId).trim();
    if (!jobId) {
      patchState({ designError: "Optimization job id is required." });
      return;
    }
    let topN = Number(state.optimizationTopN);
    if (!Number.isFinite(topN) || topN < 1) {
      patchState({ designError: "Optimization top N is invalid." });
      return;
    }
    topN = Math.round(topN);
    if (state.optimizationConstraintsJson.trim()) {
      try {
        const parsed = JSON.parse(state.optimizationConstraintsJson);
        if (parsed !== null && typeof parsed !== "object") {
          patchState({ designError: "Optimization constraints must be a JSON object." });
          return;
        }
      } catch (err) {
        patchState({
          designError: err instanceof Error ? `Invalid optimization constraints JSON: ${err.message}` : "Invalid optimization constraints JSON.",
        });
        return;
      }
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("propose_project_optimizations", {
        projectPath: state.projectPath,
        jobId,
        constraintsJson: state.optimizationConstraintsJson.trim() ? state.optimizationConstraintsJson.trim() : "{}",
        topN,
      });
      await applyDesignResult(res, false);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applySelectedOptimizationOption = async (): Promise<void> => {
    if (!hasTauri) {
      patchState({ designError: "Optimization apply requires Tauri runtime." });
      return;
    }
    const selected =
      state.selectedTableTitle === "Optimization Options" && state.selectedRow ? state.selectedRow : optimizationOptionsRows[0] ?? null;
    if (!selected) {
      patchState({ designError: "No optimization option selected." });
      return;
    }
    patchState({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("apply_project_optimization_option", {
        projectPath: state.projectPath,
        optionJson: JSON.stringify(selected),
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patchState({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
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
    void loadStandardProfiles();
    const loadRecentProjects = async (): Promise<void> => {
      if (hasTauri) {
        try {
          const stored = await tauriInvoke<string[]>("load_recent_projects_store", {});
          const sanitized = (stored ?? [])
            .map((v) => String(v ?? "").trim())
            .filter((v) => v)
            .slice(0, MAX_RECENT_PROJECTS);
          if (sanitized.length > 0) {
            patchState({ recentProjects: sanitized });
          }
          return;
        } catch {
          // Fallback to localStorage in web/dev mode.
        }
      }
      try {
        const raw = window.localStorage.getItem(RECENT_PROJECTS_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as unknown;
          if (Array.isArray(parsed)) {
            const sanitized = parsed
              .map((v) => String(v ?? "").trim())
              .filter((v) => v)
              .slice(0, MAX_RECENT_PROJECTS);
            if (sanitized.length > 0) {
              patchState({ recentProjects: sanitized });
            }
          }
        }
      } catch {
        // Best effort only.
      }
    };
    void loadRecentProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (state.workplanePreset === "custom") {
      return;
    }
    const v = Number(state.gridElevation);
    if (!Number.isFinite(v)) {
      patchState({ workplanePreset: "custom" });
      return;
    }
    if (state.workplanePreset === "floor" && Math.abs(v - 0.0) > 1e-9) {
      patchState({ workplanePreset: "custom" });
      return;
    }
    if (state.workplanePreset === "desk" && Math.abs(v - 0.75) > 1e-9) {
      patchState({ workplanePreset: "custom" });
      return;
    }
    if (state.workplanePreset === "standing" && Math.abs(v - 1.2) > 1e-9) {
      patchState({ workplanePreset: "custom" });
    }
  }, [state.gridElevation, state.workplanePreset]);

  useEffect(() => {
    return () => {
      if (estimateDebounceRef.current) {
        clearTimeout(estimateDebounceRef.current);
        estimateDebounceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!hasTauri) {
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({ liveEstimate: null, liveEstimateLoading: false, liveEstimateError: "" });
      return;
    }
    if (roomIds.length === 0 || luminaireInstances.length === 0) {
      patchState({ liveEstimate: null, liveEstimateLoading: false, liveEstimateError: "" });
      return;
    }
    scheduleLiveEstimateRefresh(projectPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasTauri, state.projectPath, state.projectDoc?.path, state.projectDocContent, roomIds.length, luminaireInstances.length]);

  useEffect(() => {
    if (!hasTauri) {
      return;
    }
    const resultDir = state.resultDir.trim();
    if (!resultDir) {
      patchState({ complianceDetailed: null, complianceDetailedLoading: false, complianceDetailedError: "" });
      return;
    }
    const projectPath = (state.projectPath || state.projectDoc?.path || "").trim();
    if (!projectPath) {
      patchState({
        complianceDetailed: null,
        complianceDetailedLoading: false,
        complianceDetailedError: "No compliance profile set. Select a standard in Calc Setup.",
      });
      return;
    }
    void loadComplianceDetailed(resultDir, projectPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasTauri, state.resultDir, state.projectPath, state.projectDoc?.path]);

  useEffect(() => {
    if (!selectedStandardProfile) {
      return;
    }
    const cur = Number(state.quickLayoutTargetLux);
    if (!Number.isFinite(cur) || Math.abs(cur - 500) < 1e-9) {
      patchState({ quickLayoutTargetLux: String(selectedStandardProfile.maintained_illuminance_lux) });
    }
  }, [selectedStandardProfile, state.quickLayoutTargetLux]);

  useEffect(() => {
    const patch: Partial<AppState> = {};
    if (!state.editRoomId && roomIds.length > 0) {
      patch.editRoomId = roomIds[0];
    }
    if (!state.arrayRoomId && roomIds.length > 0) {
      patch.arrayRoomId = roomIds[0];
    }
    if (!state.arrayAssetId && assetIds.length > 0) {
      patch.arrayAssetId = assetIds[0];
    }
    if (!state.selectedPhotometryAssetId && assetIds.length > 0) {
      patch.selectedPhotometryAssetId = assetIds[0];
    }
    if (!state.luminaireAssetId && assetIds.length > 0) {
      patch.luminaireAssetId = assetIds[0];
    }
    if (!state.aimLuminaireId && luminaireIds.length > 0) {
      patch.aimLuminaireId = luminaireIds[0];
    }
    if (!state.apertureOpeningId && openingIds.length > 0) {
      patch.apertureOpeningId = openingIds[0];
    }
    if (!state.materialIdInput && materialIds.length > 0) {
      patch.materialIdInput = materialIds[0];
    }
    if (!state.materialSurfaceIdsCsv && surfaceIds.length > 0) {
      patch.materialSurfaceIdsCsv = surfaceIds.slice(0, 4).join(",");
    }
    if (Object.keys(patch).length > 0) {
      patchState(patch);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomIds, assetIds, luminaireIds, openingIds, materialIds, surfaceIds]);

  useEffect(() => {
    if (!selectedLuminaireRaw) {
      return;
    }
    patchState({
      inspectorLumTargetX: selectedLuminaireRaw.x.toFixed(4),
      inspectorLumTargetY: selectedLuminaireRaw.y.toFixed(4),
      inspectorLumTargetZ: selectedLuminaireRaw.z.toFixed(4),
      inspectorLumTargetYaw: selectedLuminaireYawDeg.toFixed(4),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.aimLuminaireId, selectedLuminaireRaw?.x, selectedLuminaireRaw?.y, selectedLuminaireRaw?.z, selectedLuminaireYawDeg]);

  useEffect(() => {
    if (!selectedOpeningRawCenter) {
      return;
    }
    patchState({
      inspectorOpeningTargetX: selectedOpeningRawCenter.x.toFixed(4),
      inspectorOpeningTargetY: selectedOpeningRawCenter.y.toFixed(4),
      inspectorOpeningTargetZ: selectedOpeningRawCenter.z.toFixed(4),
      inspectorOpeningTargetYaw: selectedOpeningYawDeg.toFixed(4),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.apertureOpeningId, selectedOpeningRawCenter?.x, selectedOpeningRawCenter?.y, selectedOpeningRawCenter?.z, selectedOpeningYawDeg]);

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

  const complianceOverallStatus = state.complianceDetailed?.overall_status ?? "N/A";
  const complianceTone =
    complianceOverallStatus === "PASS"
      ? "text-emerald-300"
      : complianceOverallStatus === "FAIL"
        ? "text-rose-300"
        : "text-amber-200";
  const complianceBannerClass =
    complianceOverallStatus === "PASS"
      ? "border-emerald-500/40 bg-emerald-950/25 text-emerald-100"
      : complianceOverallStatus === "FAIL"
      ? "border-rose-500/40 bg-rose-950/25 text-rose-100"
      : "border-border/70 bg-panelSoft/60 text-muted";
  const liveEstimateLux = state.liveEstimate?.estimated_mean_lux ?? null;
  const liveEstimateTone =
    typeof liveEstimateLux === "number" && complianceTargetLux && Number.isFinite(complianceTargetLux)
      ? liveEstimateLux >= complianceTargetLux
        ? "border-emerald-500/40 bg-emerald-950/25 text-emerald-100"
        : liveEstimateLux >= complianceTargetLux * 0.8
          ? "border-amber-500/40 bg-amber-950/25 text-amber-100"
          : "border-rose-500/40 bg-rose-950/25 text-rose-100"
      : "border-border/70 bg-panelSoft/60 text-muted";
  const sceneZoomRef = useRef(state.sceneZoom);
  const scenePanXRef = useRef(state.scenePanX);
  const scenePanYRef = useRef(state.scenePanY);
  const sceneCamYawRef = useRef(Number(state.sceneCamYawDeg));
  const sceneCamPitchRef = useRef(Number(state.sceneCamPitchDeg));
  const sceneCamDistanceRef = useRef(Number(state.sceneCamDistance));
  const sceneCamTargetXRef = useRef(Number(state.sceneCamTargetX));
  const sceneCamTargetYRef = useRef(Number(state.sceneCamTargetY));
  const sceneCamTargetZRef = useRef(Number(state.sceneCamTargetZ));
  const sceneDragRef = useRef<{ dragging: boolean; x: number; y: number; pointerId: number | null }>({
    dragging: false,
    x: 0,
    y: 0,
    pointerId: null,
  });
  const sceneSelectRef = useRef<{ selecting: boolean; x0: number; y0: number; pointerId: number | null }>({
    selecting: false,
    x0: 0,
    y0: 0,
    pointerId: null,
  });
  const gizmoDragRef = useRef<{
    active: boolean;
    pointerId: number | null;
    target: "luminaire" | "opening" | "none";
    mode: "move" | "rotate";
    axis: "x" | "y" | "yaw";
    lastClientX: number;
    lastClientY: number;
    accumDx: number;
    accumDy: number;
    accumYaw: number;
  }>({
    active: false,
    pointerId: null,
    target: "none",
    mode: "move",
    axis: "x",
    lastClientX: 0,
    lastClientY: 0,
    accumDx: 0,
    accumDy: 0,
    accumYaw: 0,
  });
  const placementRef = useRef<{
    phase: "idle" | "dragging";
    mode: "none" | "grid" | "luminaire" | "room";
    pointerId: number | null;
    originX: number;
    originY: number;
  }>({
    phase: "idle",
    mode: "none",
    pointerId: null,
    originX: 0,
    originY: 0,
  });
  const luminaireInstanceRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});
  const prevSceneModeRef = useRef<"plan" | "3d">(state.sceneViewMode);
  useEffect(() => {
    sceneZoomRef.current = state.sceneZoom;
    scenePanXRef.current = state.scenePanX;
    scenePanYRef.current = state.scenePanY;
    sceneCamYawRef.current = Number.isFinite(Number(state.sceneCamYawDeg)) ? Number(state.sceneCamYawDeg) : 38;
    sceneCamPitchRef.current = Number.isFinite(Number(state.sceneCamPitchDeg)) ? Number(state.sceneCamPitchDeg) : 26;
    sceneCamDistanceRef.current = Number.isFinite(Number(state.sceneCamDistance)) ? Number(state.sceneCamDistance) : 18;
    sceneCamTargetXRef.current = Number.isFinite(Number(state.sceneCamTargetX)) ? Number(state.sceneCamTargetX) : 0;
    sceneCamTargetYRef.current = Number.isFinite(Number(state.sceneCamTargetY)) ? Number(state.sceneCamTargetY) : 0;
    sceneCamTargetZRef.current = Number.isFinite(Number(state.sceneCamTargetZ)) ? Number(state.sceneCamTargetZ) : 1.2;
  }, [
    state.sceneCamDistance,
    state.sceneCamPitchDeg,
    state.sceneCamTargetX,
    state.sceneCamTargetY,
    state.sceneCamTargetZ,
    state.sceneCamYawDeg,
    state.scenePanX,
    state.scenePanY,
    state.sceneZoom,
  ]);
  useEffect(() => {
    if (prevSceneModeRef.current !== state.sceneViewMode && state.sceneViewMode === "3d") {
      resetSceneView();
    }
    prevSceneModeRef.current = state.sceneViewMode;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.sceneViewMode, sceneBounds3d]);
  useEffect(() => {
    placementRef.current.mode = state.placementMode;
    if (state.placementMode === "none") {
      placementRef.current.phase = "idle";
      placementRef.current.pointerId = null;
    }
  }, [state.placementMode]);
  useEffect(() => {
    if (state.sceneViewMode === "3d" && state.placementMode !== "none") {
      placementRef.current.phase = "idle";
      placementRef.current.pointerId = null;
      patchState({ placementMode: "none" });
    }
  }, [state.placementMode, state.sceneViewMode]);
  useEffect(() => {
    const onKeyDown = (evt: KeyboardEvent): void => {
      if (evt.key !== "Escape" || state.placementMode === "none") {
        return;
      }
      placementRef.current.phase = "idle";
      placementRef.current.pointerId = null;
      patchState({ placementMode: "none" });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.placementMode]);
  useEffect(() => {
    const firstId = state.sceneSelectedLuminaireIdsCsv
      .split(",")
      .map((v) => v.trim())
      .find((v) => v);
    if (!firstId) {
      return;
    }
    const rowEl = luminaireInstanceRowRefs.current[firstId];
    if (rowEl) {
      rowEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [state.sceneSelectedLuminaireIdsCsv]);
  const clampZoom = (v: number): number => Math.max(0.35, Math.min(10, v));
  const clampPitch = (v: number): number => Math.max(-85, Math.min(85, v));
  const clampDistance = (v: number): number => Math.max(0.5, Math.min(500, v));
  const quantize = (value: number, step: number): number => {
    if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) {
      return value;
    }
    return Math.round(value / step) * step;
  };
  const resolveGizmoMoveDelta = (target: "luminaire" | "opening" | "none", rawDx: number, rawDy: number): { dx: number; dy: number } => {
    let dx = rawDx;
    let dy = rawDy;
    if (state.gizmoAxisLock === "x") {
      dy = 0;
    } else if (state.gizmoAxisLock === "y") {
      dx = 0;
    }
    if (state.gizmoMoveFrame === "local") {
      const yawDeg = target === "luminaire" ? selectedLuminaireYawDeg : target === "opening" ? selectedOpeningYawDeg : 0;
      const t = (yawDeg * Math.PI) / 180;
      const ct = Math.cos(t);
      const st = Math.sin(t);
      return {
        dx: dx * ct - dy * st,
        dy: dx * st + dy * ct,
      };
    }
    return { dx, dy };
  };
  const cameraBasis = (): {
    camX: number;
    camY: number;
    camZ: number;
    right: { x: number; y: number; z: number };
    up: { x: number; y: number; z: number };
    forward: { x: number; y: number; z: number };
  } => {
    const yaw = (sceneCamYawRef.current * Math.PI) / 180;
    const pitch = (sceneCamPitchRef.current * Math.PI) / 180;
    const dist = clampDistance(sceneCamDistanceRef.current);
    const tx = sceneCamTargetXRef.current;
    const ty = sceneCamTargetYRef.current;
    const tz = sceneCamTargetZRef.current;
    const camX = tx + dist * Math.cos(pitch) * Math.cos(yaw);
    const camY = ty + dist * Math.cos(pitch) * Math.sin(yaw);
    const camZ = tz + dist * Math.sin(pitch);
    let fx = tx - camX;
    let fy = ty - camY;
    let fz = tz - camZ;
    const fl = Math.hypot(fx, fy, fz) || 1;
    fx /= fl;
    fy /= fl;
    fz /= fl;
    let rx = fy * 1 - fz * 0;
    let ry = fz * 0 - fx * 1;
    let rz = fx * 0 - fy * 0;
    const rl = Math.hypot(rx, ry, rz) || 1;
    rx /= rl;
    ry /= rl;
    rz /= rl;
    const ux = ry * fz - rz * fy;
    const uy = rz * fx - rx * fz;
    const uz = rx * fy - ry * fx;
    return {
      camX,
      camY,
      camZ,
      right: { x: rx, y: ry, z: rz },
      up: { x: ux, y: uy, z: uz },
      forward: { x: fx, y: fy, z: fz },
    };
  };
  const resetSceneView = (): void => {
    if (state.sceneViewMode === "plan") {
      patchState({ sceneZoom: 1, scenePanX: 0, scenePanY: 0 });
      return;
    }
    if (!sceneBounds3d) {
      patchState({
        sceneCamYawDeg: "38",
        sceneCamPitchDeg: "26",
        sceneCamDistance: "18",
        sceneCamTargetX: "0",
        sceneCamTargetY: "0",
        sceneCamTargetZ: "1.2",
      });
      return;
    }
    const tx = (sceneBounds3d.minX + sceneBounds3d.maxX) * 0.5;
    const ty = (sceneBounds3d.minY + sceneBounds3d.maxY) * 0.5;
    const tz = (sceneBounds3d.minZ + sceneBounds3d.maxZ) * 0.5;
    const radius = Math.max(
      Math.hypot(sceneBounds3d.maxX - sceneBounds3d.minX, sceneBounds3d.maxY - sceneBounds3d.minY),
      sceneBounds3d.maxZ - sceneBounds3d.minZ,
      1.0,
    );
    patchState({
      sceneCamYawDeg: "38",
      sceneCamPitchDeg: "26",
      sceneCamDistance: (radius * 1.6).toFixed(3),
      sceneCamTargetX: tx.toFixed(3),
      sceneCamTargetY: ty.toFixed(3),
      sceneCamTargetZ: tz.toFixed(3),
    });
  };
  const projectSvgCoord = (evt: { clientX: number; clientY: number; currentTarget: EventTarget & SVGSVGElement }): { x: number; y: number } => {
    const rect = evt.currentTarget.getBoundingClientRect();
    return {
      x: ((evt.clientX - rect.left) / Math.max(rect.width, 1e-6)) * 100,
      y: ((evt.clientY - rect.top) / Math.max(rect.height, 1e-6)) * 70,
    };
  };
  const svgToWorldPlan = (svgX: number, svgY: number): { x: number; y: number } | null => {
    if (!sceneBounds) {
      return null;
    }
    const spanX = Math.max(sceneBounds.maxX - sceneBounds.minX, 1e-9);
    const spanY = Math.max(sceneBounds.maxY - sceneBounds.minY, 1e-9);
    const zoom = Math.max(sceneZoomRef.current, 1e-9);
    const baseX = (svgX - 50 - scenePanXRef.current) / zoom + 50;
    const baseY = (svgY - 35 - scenePanYRef.current) / zoom + 35;
    return {
      x: sceneBounds.minX + ((baseX - 6) / 88) * spanX,
      y: sceneBounds.minY + ((64 - baseY) / 58) * spanY,
    };
  };
  const onSceneWheel = (evt: ReactWheelEvent<SVGSVGElement>): void => {
    evt.preventDefault();
    if (state.sceneViewMode === "3d") {
      const d0 = clampDistance(sceneCamDistanceRef.current);
      const d1 = clampDistance(d0 * Math.exp(evt.deltaY * 0.0014));
      patchState({ sceneCamDistance: d1.toFixed(4) });
      return;
    }
    const at = projectSvgCoord(evt);
    const z0 = sceneZoomRef.current;
    const z1 = clampZoom(z0 * Math.exp(-evt.deltaY * 0.0014));
    if (Math.abs(z1 - z0) < 1e-6) {
      return;
    }
    const p0x = scenePanXRef.current;
    const p0y = scenePanYRef.current;
    const p1x = at.x - ((at.x - 50 - p0x) / z0) * z1 - 50;
    const p1y = at.y - ((at.y - 35 - p0y) / z0) * z1 - 35;
    patchState({ sceneZoom: z1, scenePanX: p1x, scenePanY: p1y });
  };
  const onScenePointerDown = (evt: ReactPointerEvent<SVGSVGElement>): void => {
    if (state.placementMode === "grid") {
      if (state.sceneViewMode !== "plan") {
        patchState({ calcSetupError: "Switch to plan view for click-to-place." });
        return;
      }
      if (placementRef.current.phase !== "dragging") {
        const p = projectSvgCoord(evt);
        const world = svgToWorldPlan(p.x, p.y);
        if (!world) {
          patchState({ calcSetupError: "Unable to place grid: viewport bounds unavailable." });
          return;
        }
        placementRef.current.phase = "dragging";
        placementRef.current.mode = "grid";
        placementRef.current.pointerId = evt.pointerId;
        placementRef.current.originX = world.x;
        placementRef.current.originY = world.y;
        patchState({
          calcSetupError: "",
          gridOriginX: world.x.toFixed(4),
          gridOriginY: world.y.toFixed(4),
          gridWidth: "0",
          gridHeight: "0",
        });
        evt.currentTarget.setPointerCapture(evt.pointerId);
        return;
      }
    }
    if (evt.shiftKey) {
      const p = projectSvgCoord(evt);
      sceneSelectRef.current = { selecting: true, x0: p.x, y0: p.y, pointerId: evt.pointerId };
      patchState({
        sceneSelectActive: true,
        sceneSelectX0: p.x,
        sceneSelectY0: p.y,
        sceneSelectX1: p.x,
        sceneSelectY1: p.y,
      });
    } else {
      sceneDragRef.current = { dragging: true, x: evt.clientX, y: evt.clientY, pointerId: evt.pointerId };
    }
    evt.currentTarget.setPointerCapture(evt.pointerId);
  };
  const onScenePointerMove = (evt: ReactPointerEvent<SVGSVGElement>): void => {
    if (placementRef.current.phase === "dragging" && placementRef.current.mode === "grid" && placementRef.current.pointerId === evt.pointerId) {
      const p = projectSvgCoord(evt);
      const world = svgToWorldPlan(p.x, p.y);
      if (!world) {
        return;
      }
      const x0 = placementRef.current.originX;
      const y0 = placementRef.current.originY;
      const minX = Math.min(x0, world.x);
      const minY = Math.min(y0, world.y);
      const width = Math.abs(world.x - x0);
      const height = Math.abs(world.y - y0);
      patchState({
        gridOriginX: minX.toFixed(4),
        gridOriginY: minY.toFixed(4),
        gridWidth: width.toFixed(4),
        gridHeight: height.toFixed(4),
      });
      return;
    }
    const g = gizmoDragRef.current;
    if (g.active && g.pointerId === evt.pointerId) {
      const dxPx = evt.clientX - g.lastClientX;
      const dyPx = evt.clientY - g.lastClientY;
      g.lastClientX = evt.clientX;
      g.lastClientY = evt.clientY;
      const moveStep = Number(state.gizmoMoveStepM);
      const rotateStep = Number(state.gizmoRotateStepDeg);
      const mScale = Number.isFinite(moveStep) && moveStep > 0 ? moveStep / 28 : 0.01;
      const rScale = Number.isFinite(rotateStep) && rotateStep > 0 ? rotateStep / 9 : 0.5;
      if (g.mode === "move") {
        if (g.axis === "x") {
          g.accumDx += dxPx * mScale;
        } else if (g.axis === "y") {
          g.accumDy += -dyPx * mScale;
        }
      } else if (g.mode === "rotate" && g.axis === "yaw") {
        g.accumYaw += dxPx * rScale;
      }
      const moveSnap = Number(state.gizmoMoveSnapM);
      const angleSnap = Number(state.gizmoAngleSnapDeg);
      const previewRawDx = state.gizmoSnapEnabled ? quantize(g.accumDx, moveSnap) : g.accumDx;
      const previewRawDy = state.gizmoSnapEnabled ? quantize(g.accumDy, moveSnap) : g.accumDy;
      const previewYaw = state.gizmoSnapEnabled ? quantize(g.accumYaw, angleSnap) : g.accumYaw;
      const previewMove = resolveGizmoMoveDelta(g.target, previewRawDx, previewRawDy);
      patchState({
        gizmoPreviewDx: previewMove.dx,
        gizmoPreviewDy: previewMove.dy,
        gizmoPreviewYawDeg: previewYaw,
        gizmoPreviewTarget: g.target,
      });
      return;
    }
    const s = sceneSelectRef.current;
    if (s.selecting && s.pointerId === evt.pointerId) {
      const p = projectSvgCoord(evt);
      patchState({
        sceneSelectActive: true,
        sceneSelectX0: s.x0,
        sceneSelectY0: s.y0,
        sceneSelectX1: p.x,
        sceneSelectY1: p.y,
      });
      return;
    }
    const d = sceneDragRef.current;
    if (!d.dragging || d.pointerId !== evt.pointerId) {
      return;
    }
    if (state.sceneViewMode === "3d") {
      const dxPx = evt.clientX - d.x;
      const dyPx = evt.clientY - d.y;
      d.x = evt.clientX;
      d.y = evt.clientY;
      if (evt.altKey) {
        const rect = evt.currentTarget.getBoundingClientRect();
        const scale = clampDistance(sceneCamDistanceRef.current) * 0.0022;
        const basis = cameraBasis();
        const tx = sceneCamTargetXRef.current + (-dxPx / Math.max(rect.width, 1)) * scale * basis.right.x + (dyPx / Math.max(rect.height, 1)) * scale * basis.up.x;
        const ty = sceneCamTargetYRef.current + (-dxPx / Math.max(rect.width, 1)) * scale * basis.right.y + (dyPx / Math.max(rect.height, 1)) * scale * basis.up.y;
        const tz = sceneCamTargetZRef.current + (-dxPx / Math.max(rect.width, 1)) * scale * basis.right.z + (dyPx / Math.max(rect.height, 1)) * scale * basis.up.z;
        patchState({
          sceneCamTargetX: tx.toFixed(4),
          sceneCamTargetY: ty.toFixed(4),
          sceneCamTargetZ: tz.toFixed(4),
        });
      } else {
        const yaw = sceneCamYawRef.current - dxPx * 0.28;
        const pitch = clampPitch(sceneCamPitchRef.current - dyPx * 0.22);
        patchState({ sceneCamYawDeg: yaw.toFixed(3), sceneCamPitchDeg: pitch.toFixed(3) });
      }
      return;
    }
    const rect = evt.currentTarget.getBoundingClientRect();
    const dxSvg = ((evt.clientX - d.x) / Math.max(rect.width, 1e-6)) * 100;
    const dySvg = ((evt.clientY - d.y) / Math.max(rect.height, 1e-6)) * 70;
    d.x = evt.clientX;
    d.y = evt.clientY;
    patchState({ scenePanX: scenePanXRef.current + dxSvg, scenePanY: scenePanYRef.current + dySvg });
  };
  const onScenePointerUp = (evt: ReactPointerEvent<SVGSVGElement>): void => {
    if (placementRef.current.phase === "dragging" && placementRef.current.mode === "grid" && placementRef.current.pointerId === evt.pointerId) {
      const p = projectSvgCoord(evt);
      const world = svgToWorldPlan(p.x, p.y);
      if (world) {
        const x0 = placementRef.current.originX;
        const y0 = placementRef.current.originY;
        const minX = Math.min(x0, world.x);
        const minY = Math.min(y0, world.y);
        const width = Math.abs(world.x - x0);
        const height = Math.abs(world.y - y0);
        patchState({
          placementMode: "none",
          gridOriginX: minX.toFixed(4),
          gridOriginY: minY.toFixed(4),
          gridWidth: width.toFixed(4),
          gridHeight: height.toFixed(4),
        });
      } else {
        patchState({ placementMode: "none" });
      }
      placementRef.current.phase = "idle";
      placementRef.current.pointerId = null;
      if (evt.currentTarget.hasPointerCapture(evt.pointerId)) {
        evt.currentTarget.releasePointerCapture(evt.pointerId);
      }
      return;
    }
    const g = gizmoDragRef.current;
    if (g.active && g.pointerId === evt.pointerId) {
      const moveSnap = Number(state.gizmoMoveSnapM);
      const angleSnap = Number(state.gizmoAngleSnapDeg);
      const rawDx = state.gizmoSnapEnabled ? quantize(g.accumDx, moveSnap) : g.accumDx;
      const rawDy = state.gizmoSnapEnabled ? quantize(g.accumDy, moveSnap) : g.accumDy;
      const dyaw = state.gizmoSnapEnabled ? quantize(g.accumYaw, angleSnap) : g.accumYaw;
      const target = g.target;
      const move = resolveGizmoMoveDelta(target, rawDx, rawDy);
      const dx = move.dx;
      const dy = move.dy;
      gizmoDragRef.current = {
        active: false,
        pointerId: null,
        target: "none",
        mode: "move",
        axis: "x",
        lastClientX: 0,
        lastClientY: 0,
        accumDx: 0,
        accumDy: 0,
        accumYaw: 0,
      };
      patchState({
        gizmoPreviewDx: 0,
        gizmoPreviewDy: 0,
        gizmoPreviewYawDeg: 0,
        gizmoPreviewTarget: "none",
      });
      if (target === "luminaire" && (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6 || Math.abs(dyaw) > 1e-6)) {
        void nudgeLuminaireGizmo(dx, dy, 0, dyaw);
      }
      if (target === "opening" && (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6 || Math.abs(dyaw) > 1e-6)) {
        void transformOpeningGizmo(dx, dy, 0, dyaw);
      }
      return;
    }
    const s = sceneSelectRef.current;
    if (s.selecting && s.pointerId === evt.pointerId) {
      const p = projectSvgCoord(evt);
      const xMin = Math.min(s.x0, p.x);
      const xMax = Math.max(s.x0, p.x);
      const yMin = Math.min(s.y0, p.y);
      const yMax = Math.max(s.y0, p.y);
      const inRect = (x: number, y: number): boolean => x >= xMin && x <= xMax && y >= yMin && y <= yMax;
      const selectedLumIds = sceneLuminaires
        .filter((lum) => {
          const m = sceneProject(lum.x, lum.y, lum.z);
          return !!m && inRect(m.x, m.y);
        })
        .map((lum) => lum.id);
      const selectedSurfaceIds = sceneSurfaces
        .filter((surface) => {
          if (surface.points.length === 0) {
            return false;
          }
          const cx = surface.points.reduce((acc, v) => acc + v.x, 0) / surface.points.length;
          const cy = surface.points.reduce((acc, v) => acc + v.y, 0) / surface.points.length;
          const cz = surface.points.reduce((acc, v) => acc + v.z, 0) / surface.points.length;
          const m = sceneProject(cx, cy, cz);
          return !!m && inRect(m.x, m.y);
        })
        .map((surface) => surface.id);
      patchState({
        materialSurfaceIdsCsv: selectedSurfaceIds.length > 0 ? selectedSurfaceIds.join(",") : state.materialSurfaceIdsCsv,
        sceneSelectedLuminaireIdsCsv: selectedLumIds.join(","),
        aimLuminaireId: selectedLumIds[0] ?? state.aimLuminaireId,
        sceneSelectActive: false,
      });
      sceneSelectRef.current = { selecting: false, x0: 0, y0: 0, pointerId: null };
      evt.currentTarget.releasePointerCapture(evt.pointerId);
      return;
    }
    if (sceneDragRef.current.pointerId === evt.pointerId) {
      sceneDragRef.current = { dragging: false, x: 0, y: 0, pointerId: null };
      evt.currentTarget.releasePointerCapture(evt.pointerId);
    }
  };
  const sceneProjectWithDepth = (x: number, y: number, z: number): { x: number; y: number; depth: number } | null => {
    if (state.sceneViewMode === "plan") {
      if (!sceneBounds) {
        return null;
      }
      const spanX = Math.max(sceneBounds.maxX - sceneBounds.minX, 1e-9);
      const spanY = Math.max(sceneBounds.maxY - sceneBounds.minY, 1e-9);
      const baseX = 6 + ((x - sceneBounds.minX) / spanX) * 88;
      const baseY = 64 - ((y - sceneBounds.minY) / spanY) * 58;
      return {
        x: (baseX - 50) * state.sceneZoom + 50 + state.scenePanX,
        y: (baseY - 35) * state.sceneZoom + 35 + state.scenePanY,
        depth: 0,
      };
    }
    if (!sceneBounds3d) {
      return null;
    }
    const basis = cameraBasis();
    const rx = x - basis.camX;
    const ry = y - basis.camY;
    const rz = z - basis.camZ;
    const cx = rx * basis.right.x + ry * basis.right.y + rz * basis.right.z;
    const cy = rx * basis.up.x + ry * basis.up.y + rz * basis.up.z;
    const cz = rx * basis.forward.x + ry * basis.forward.y + rz * basis.forward.z;
    if (cz <= 0.05) {
      return null;
    }
    const fov = (58 * Math.PI) / 180;
    const f = 1 / Math.tan(fov * 0.5);
    const aspect = 100 / 70;
    const nx = (cx / cz) * f / aspect;
    const ny = (cy / cz) * f;
    return {
      x: 50 + nx * 44,
      y: 35 - ny * 31,
      depth: cz,
    };
  };
  const sceneProject = (x: number, y: number, z = 0): { x: number; y: number } | null => {
    const p = sceneProjectWithDepth(x, y, z);
    return p ? { x: p.x, y: p.y } : null;
  };
  const centerViewportOnLuminaire = (lum: LuminaireInstanceRow): void => {
    if (state.sceneViewMode === "plan") {
      if (!sceneBounds) {
        return;
      }
      const spanX = Math.max(sceneBounds.maxX - sceneBounds.minX, 1e-9);
      const spanY = Math.max(sceneBounds.maxY - sceneBounds.minY, 1e-9);
      const baseX = 6 + ((lum.x - sceneBounds.minX) / spanX) * 88;
      const baseY = 64 - ((lum.y - sceneBounds.minY) / spanY) * 58;
      patchState({
        scenePanX: -(baseX - 50) * state.sceneZoom,
        scenePanY: -(baseY - 35) * state.sceneZoom,
      });
      return;
    }
    patchState({
      sceneCamTargetX: lum.x.toFixed(4),
      sceneCamTargetY: lum.y.toFixed(4),
      sceneCamTargetZ: lum.z.toFixed(4),
    });
  };
  const selectLuminaireGroup = (ids: string[]): void => {
    const cleanIds = ids.map((id) => id.trim()).filter((id) => id);
    if (cleanIds.length === 0) {
      return;
    }
    patchState({
      sceneSelectedLuminaireIdsCsv: cleanIds.join(","),
      aimLuminaireId: cleanIds[0],
    });
  };
  const selectLuminaireInstance = (lum: LuminaireInstanceRow): void => {
    patchState({
      sceneSelectedLuminaireIdsCsv: lum.id,
      aimLuminaireId: lum.id,
    });
    centerViewportOnLuminaire(lum);
  };
  const scenePolygonDepth = (poly: ScenePolygon): number => {
    if (state.sceneViewMode !== "3d") {
      return 0;
    }
    let depthSum = 0;
    let count = 0;
    for (const p of poly.points) {
      const m = sceneProjectWithDepth(p.x, p.y, p.z);
      if (!m) {
        continue;
      }
      depthSum += m.depth;
      count += 1;
    }
    return count > 0 ? depthSum / count : -1;
  };
  const falseColorOpacity = Math.max(0.1, Math.min(1, Number(state.falseColorOpacity) || 0.7));

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
                  <svg
                    viewBox="0 0 100 70"
                    className="h-44 w-full rounded bg-panel"
                    style={{
                      touchAction: "none",
                      cursor:
                        state.placementMode === "grid" && state.sceneViewMode === "plan"
                          ? "crosshair"
                          : sceneDragRef.current.dragging
                            ? "grabbing"
                            : "grab",
                    }}
                    onWheel={onSceneWheel}
                    onPointerDown={onScenePointerDown}
                    onPointerMove={onScenePointerMove}
                    onPointerUp={onScenePointerUp}
                  >
                    <rect x="0" y="0" width="100" height="70" fill="transparent" stroke="rgba(120,130,150,0.4)" />
                    {state.layerGrids && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? [...sceneGrids]
                          .sort((a, b) => scenePolygonDepth(b) - scenePolygonDepth(a))
                          .map((grid) => {
                          const mapped = grid.points
                            .map((p) => sceneProject(p.x, p.y, p.z))
                            .filter((p): p is { x: number; y: number } => !!p);
                          if (mapped.length < 3) {
                            return null;
                          }
                          return (
                            <path
                              key={`grid-${grid.id}`}
                              d={pointsToSvgPath(mapped)}
                              fill="rgba(251,191,36,0.06)"
                              stroke="rgba(251,191,36,0.82)"
                              strokeDasharray="1.2 0.9"
                              strokeWidth={0.22}
                            />
                          );
                        })
                      : null}
                    {(state.layerGrids || state.placementMode === "grid") && sceneGridPreview.outline && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? (() => {
                          const mapped = sceneGridPreview.outline.points
                            .map((p) => sceneProject(p.x, p.y, p.z))
                            .filter((p): p is { x: number; y: number } => !!p);
                          if (mapped.length < 3) {
                            return null;
                          }
                          return (
                            <path
                              d={pointsToSvgPath(mapped)}
                              fill="rgba(110,231,183,0.05)"
                              stroke="rgba(110,231,183,0.72)"
                              strokeDasharray="0.9 0.75"
                              strokeWidth={0.2}
                            />
                          );
                        })()
                      : null}
                    {state.layerFalseColor && state.falseColorData && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? state.falseColorData.grids.map((grid, gi) => {
                          const ox = Number(grid.origin?.[0] ?? 0);
                          const oy = Number(grid.origin?.[1] ?? 0);
                          const elev = Number(grid.elevation ?? grid.origin?.[2] ?? 0);
                          const nx = Math.max(1, Number(grid.nx ?? 1));
                          const ny = Math.max(1, Number(grid.ny ?? 1));
                          const cellW = Number(grid.width ?? 0) / nx;
                          const cellH = Number(grid.height ?? 0) / ny;
                          return (
                            <g key={`falsecolor-grid-${gi}-${grid.name}`}>
                              {grid.cells.map((cell, i) => {
                                const row = Math.floor(i / nx);
                                const col = i % nx;
                                const x0 = ox + col * cellW;
                                const y0 = oy + row * cellH;
                                const x1 = ox + (col + 1) * cellW;
                                const y1 = oy + (row + 1) * cellH;
                                const corners = [
                                  sceneProject(x0, y0, elev),
                                  sceneProject(x1, y0, elev),
                                  sceneProject(x1, y1, elev),
                                  sceneProject(x0, y1, elev),
                                ];
                                if (corners.some((p) => !p)) {
                                  return null;
                                }
                                const mapped = corners as Array<{ x: number; y: number }>;
                                const center = sceneProject(ox + (col + 0.5) * cellW, oy + (row + 0.5) * cellH, elev);
                                return (
                                  <g key={`falsecolor-cell-${gi}-${i}`}>
                                    <polygon
                                      points={mapped.map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(" ")}
                                      fill={cell.color}
                                      opacity={falseColorOpacity}
                                      stroke="none"
                                    />
                                    {state.falseColorShowValues && i % 4 === 0 && center ? (
                                      <text x={center.x} y={center.y} textAnchor="middle" fontSize={1.15} fill="white" opacity={0.95}>
                                        {Number(cell.lux).toFixed(0)}
                                      </text>
                                    ) : null}
                                  </g>
                                );
                              })}
                              {state.falseColorShowContours
                                ? grid.contours.map((contour, ci) => (
                                    <g key={`falsecolor-contour-${gi}-${ci}`}>
                                      {contour.paths.map((path, pi) => {
                                        const mapped = path
                                          .map((pt) => sceneProject(Number(pt[0] ?? 0), Number(pt[1] ?? 0), elev))
                                          .filter((p): p is { x: number; y: number } => !!p);
                                        if (mapped.length < 2) {
                                          return null;
                                        }
                                        const mid = mapped[Math.floor(mapped.length * 0.5)];
                                        return (
                                          <g key={`falsecolor-contour-path-${gi}-${ci}-${pi}`}>
                                            <polyline
                                              points={mapped.map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(" ")}
                                              fill="none"
                                              stroke="white"
                                              strokeWidth={0.15}
                                              opacity={0.8}
                                            />
                                            <text x={mid.x} y={mid.y} textAnchor="middle" fontSize={1.15} fill="white" opacity={0.95}>
                                              {Number(contour.level).toFixed(0)}
                                            </text>
                                          </g>
                                        );
                                      })}
                                    </g>
                                  ))
                                : null}
                            </g>
                          );
                        })
                      : null}
                    {(state.layerGridPoints || state.placementMode === "grid") && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? (
                          <>
                            {sceneGridPoints.map((set, si) => (
                              <g key={`grid-points-${set.id}-${si}`}>
                                {set.points.map((p, pi) => {
                                  const mapped = sceneProject(p.x, p.y, p.z);
                                  if (!mapped) {
                                    return null;
                                  }
                                  return <circle key={`grid-point-${set.id}-${pi}`} cx={mapped.x} cy={mapped.y} r={1.5} fill={p.color} opacity={0.6} />;
                                })}
                                {set.labelAnchor && set.labelText
                                  ? (() => {
                                      const mapped = sceneProject(set.labelAnchor.x, set.labelAnchor.y, set.labelAnchor.z);
                                      if (!mapped) {
                                        return null;
                                      }
                                      return (
                                        <text x={mapped.x} y={mapped.y} textAnchor="middle" fontSize={1.2} fill="#4ade80" opacity={0.9}>
                                          {set.labelText}
                                        </text>
                                      );
                                    })()
                                  : null}
                              </g>
                            ))}
                            {sceneGridPreview.points.map((p, i) => {
                              const mapped = sceneProject(p.x, p.y, p.z);
                              if (!mapped) {
                                return null;
                              }
                              return <circle key={`grid-preview-point-${i}`} cx={mapped.x} cy={mapped.y} r={1.15} fill={p.color} opacity={0.45} />;
                            })}
                            {sceneGridPreview.labelAnchor && sceneGridPreview.labelText
                              ? (() => {
                                  const mapped = sceneProject(sceneGridPreview.labelAnchor.x, sceneGridPreview.labelAnchor.y, sceneGridPreview.labelAnchor.z);
                                  if (!mapped) {
                                    return null;
                                  }
                                  return (
                                    <text x={mapped.x} y={mapped.y} textAnchor="middle" fontSize={1.2} fill="#86efac" opacity={0.95}>
                                      {sceneGridPreview.labelText}
                                    </text>
                                  );
                                })()
                              : null}
                          </>
                        )
                      : null}
                    {state.layerRooms && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? [...sceneRooms]
                          .sort((a, b) => scenePolygonDepth(b) - scenePolygonDepth(a))
                          .map((room) => {
                          const mapped = room.points
                            .map((p) => sceneProject(p.x, p.y, p.z))
                            .filter((p): p is { x: number; y: number } => !!p);
                          if (mapped.length < 3) {
                            return null;
                          }
                          return (
                            <path
                              key={`room-${room.id}`}
                              d={pointsToSvgPath(mapped)}
                              fill={state.editRoomId === room.id || state.arrayRoomId === room.id ? "rgba(96,165,250,0.28)" : "rgba(59,130,246,0.16)"}
                              stroke={state.editRoomId === room.id || state.arrayRoomId === room.id ? "rgba(147,197,253,0.95)" : "rgba(96,165,250,0.75)"}
                              strokeWidth={0.32}
                              onClick={() => patchState({ editRoomId: room.id, arrayRoomId: room.id })}
                            />
                          );
                        })
                      : null}
                    {state.layerSurfaces && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? [...sceneSurfaces]
                          .sort((a, b) => scenePolygonDepth(b) - scenePolygonDepth(a))
                          .map((surface) => {
                          const mapped = surface.points
                            .map((p) => sceneProject(p.x, p.y, p.z))
                            .filter((p): p is { x: number; y: number } => !!p);
                          if (mapped.length < 3) {
                            return null;
                          }
                          return (
                            <path
                              key={`surface-${surface.id}`}
                              d={pointsToSvgPath(mapped)}
                              fill={state.materialSurfaceIdsCsv.split(",").map((x) => x.trim()).includes(surface.id) ? "rgba(250,204,21,0.28)" : "rgba(148,163,184,0.08)"}
                              stroke={state.materialSurfaceIdsCsv.split(",").map((x) => x.trim()).includes(surface.id) ? "rgba(250,204,21,0.95)" : "rgba(148,163,184,0.45)"}
                              strokeWidth={0.18}
                              onClick={() => patchState({ materialSurfaceIdsCsv: surface.id })}
                            />
                          );
                        })
                      : null}
                    {state.layerOpenings && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? [...sceneOpenings]
                          .sort((a, b) => scenePolygonDepth(b) - scenePolygonDepth(a))
                          .map((opening) => {
                          const mapped = opening.points
                            .map((p) => sceneProject(p.x, p.y, p.z))
                            .filter((p): p is { x: number; y: number } => !!p);
                          if (mapped.length < 3) {
                            return null;
                          }
                          return (
                            <path
                              key={`opening-${opening.id}`}
                              d={pointsToSvgPath(mapped)}
                              fill={state.apertureOpeningId === opening.id ? "rgba(16,185,129,0.34)" : "rgba(16,185,129,0.14)"}
                              stroke={state.apertureOpeningId === opening.id ? "rgba(110,231,183,0.98)" : "rgba(52,211,153,0.8)"}
                              strokeWidth={0.24}
                              onClick={() => patchState({ apertureOpeningId: opening.id })}
                            />
                          );
                        })
                      : null}
                    {state.layerBeamSpread && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? beamSpreadRows.map((beam, idx) => {
                          const yawRad = (beam.yawDeg * Math.PI) / 180;
                          const renderEllipsePlan = (radiusC0: number, radiusC90: number, kind: "beam" | "field") => {
                            if (!(radiusC0 > 0) || !(radiusC90 > 0)) {
                              return null;
                            }
                            const center = sceneProject(beam.x, beam.y, BEAM_WORKPLANE_Z);
                            const axis0p = beamEllipseWorldPoint(beam.x, beam.y, yawRad, radiusC0, radiusC90, 0);
                            const axis90p = beamEllipseWorldPoint(beam.x, beam.y, yawRad, radiusC0, radiusC90, Math.PI * 0.5);
                            const axis0 = sceneProject(axis0p.x, axis0p.y, BEAM_WORKPLANE_Z);
                            const axis90 = sceneProject(axis90p.x, axis90p.y, BEAM_WORKPLANE_Z);
                            if (!center || !axis0 || !axis90) {
                              return null;
                            }
                            const rx = Math.hypot(axis0.x - center.x, axis0.y - center.y);
                            const ry = Math.hypot(axis90.x - center.x, axis90.y - center.y);
                            if (!(rx > 0.01) || !(ry > 0.01)) {
                              return null;
                            }
                            const screenAngleDeg = (Math.atan2(axis0.y - center.y, axis0.x - center.x) * 180) / Math.PI;
                            return (
                              <ellipse
                                key={`beamspread-plan-${kind}-${beam.id || idx}`}
                                cx={center.x}
                                cy={center.y}
                                rx={rx}
                                ry={ry}
                                fill="#fbbf24"
                                opacity={kind === "beam" ? 0.15 : 0.05}
                                stroke="#fbbf24"
                                strokeOpacity={kind === "beam" ? 0.4 : 0.2}
                                strokeWidth={0.22}
                                strokeDasharray={kind === "field" ? "4 2" : undefined}
                                transform={`rotate(${screenAngleDeg.toFixed(3)} ${center.x.toFixed(3)} ${center.y.toFixed(3)})`}
                              />
                            );
                          };
                          const renderEllipse3d = (radiusC0: number, radiusC90: number, kind: "beam" | "field") => {
                            if (!(radiusC0 > 0) || !(radiusC90 > 0)) {
                              return null;
                            }
                            const mapped = [];
                            const segments = 24;
                            for (let s = 0; s < segments; s += 1) {
                              const t = (s / segments) * Math.PI * 2;
                              const wp = beamEllipseWorldPoint(beam.x, beam.y, yawRad, radiusC0, radiusC90, t);
                              const p = sceneProject(wp.x, wp.y, BEAM_WORKPLANE_Z);
                              if (p) {
                                mapped.push(p);
                              }
                            }
                            if (mapped.length < 3) {
                              return null;
                            }
                            return (
                              <polygon
                                key={`beamspread-3d-${kind}-${beam.id || idx}`}
                                points={mapped.map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(" ")}
                                fill="#fbbf24"
                                opacity={kind === "beam" ? 0.15 : 0.05}
                                stroke="#fbbf24"
                                strokeOpacity={kind === "beam" ? 0.4 : 0.2}
                                strokeWidth={0.18}
                                strokeDasharray={kind === "field" ? "4 2" : undefined}
                              />
                            );
                          };
                          const field =
                            state.sceneViewMode === "plan"
                              ? renderEllipsePlan(beam.fieldRadiusC0, beam.fieldRadiusC90, "field")
                              : renderEllipse3d(beam.fieldRadiusC0, beam.fieldRadiusC90, "field");
                          const cone =
                            state.sceneViewMode === "plan"
                              ? renderEllipsePlan(beam.beamRadiusC0, beam.beamRadiusC90, "beam")
                              : renderEllipse3d(beam.beamRadiusC0, beam.beamRadiusC90, "beam");
                          if (!field && !cone) {
                            return null;
                          }
                          return (
                            <g key={`beamspread-${beam.id || idx}`}>
                              {field}
                              {cone}
                            </g>
                          );
                        })
                      : null}
                    {(state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds) && quickLayoutPreviewLuminaires.length > 0
                      ? quickLayoutPreviewLuminaires.map((lum) => {
                          const mapped = sceneProject(lum.x, lum.y, lum.z);
                          if (!mapped) {
                            return null;
                          }
                          return (
                            <g key={`quick-preview-${lum.id}`}>
                              <circle cx={mapped.x} cy={mapped.y} r={1.7} fill="none" stroke="#f97316" strokeWidth={0.2} strokeDasharray="3 2" opacity={0.95} />
                              <circle cx={mapped.x} cy={mapped.y} r={0.8} fill="#f97316" opacity={0.35} />
                            </g>
                          );
                        })
                      : null}
                    {state.layerLuminaires && (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds)
                      ? sceneLuminaires.map((lum) => {
                          const mapped = sceneProject(lum.x, lum.y, lum.z);
                          if (!mapped) {
                            return null;
                          }
                          const selected = selectedLuminaireIdsSet.has(lum.id) || state.aimLuminaireId === lum.id;
                          return (
                            <g key={`lum-${lum.id}`} onClick={() => patchState({ aimLuminaireId: lum.id, sceneSelectedLuminaireIdsCsv: lum.id })}>
                              <circle cx={mapped.x} cy={mapped.y} r={selected ? 1.5 : 1.1} fill={selected ? "#f59e0b" : "#fbbf24"} />
                              <circle cx={mapped.x} cy={mapped.y} r={selected ? 2.6 : 2.2} fill="transparent" stroke={selected ? "rgba(251,191,36,0.95)" : "rgba(251,191,36,0.55)"} strokeWidth={0.16} />
                            </g>
                          );
                        })
                      : null}
                    {(state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds) && selectedPoint
                      ? (() => {
                          const m = sceneProject(selectedPoint.x, selectedPoint.y, selectedPoint.z ?? 0);
                          if (!m) {
                            return null;
                          }
                          return (
                            <g>
                              <line x1={m.x - 1.3} y1={m.y} x2={m.x + 1.3} y2={m.y} stroke="#60a5fa" strokeWidth={0.24} />
                              <line x1={m.x} y1={m.y - 1.3} x2={m.x} y2={m.y + 1.3} stroke="#60a5fa" strokeWidth={0.24} />
                            </g>
                          );
                        })()
                      : null}
                    {selectedLuminairePoint
                      ? (() => {
                          const p = sceneProject(selectedLuminairePoint.x, selectedLuminairePoint.y, selectedLuminairePoint.z);
                          if (!p) {
                            return null;
                          }
                          return (
                            <g>
                              <line x1={p.x} y1={p.y} x2={p.x + 4.2} y2={p.y} stroke="rgba(248,113,113,0.95)" strokeWidth={0.24} />
                              <line x1={p.x} y1={p.y} x2={p.x} y2={p.y - 4.2} stroke="rgba(96,165,250,0.95)" strokeWidth={0.24} />
                              <circle
                                cx={p.x + 4.8}
                                cy={p.y}
                                r={0.9}
                                fill="rgba(248,113,113,0.92)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "move",
                                    axis: "x",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(step, 0, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x - 4.8}
                                cy={p.y}
                                r={0.9}
                                fill="rgba(248,113,113,0.92)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "move",
                                    axis: "x",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(-step, 0, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y - 4.8}
                                r={0.9}
                                fill="rgba(96,165,250,0.92)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "move",
                                    axis: "y",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(0, step, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y + 4.8}
                                r={0.9}
                                fill="rgba(96,165,250,0.92)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "move",
                                    axis: "y",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(0, -step, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y}
                                r={2.4}
                                fill="transparent"
                                stroke="rgba(251,191,36,0.95)"
                                strokeWidth={0.2}
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "rotate",
                                    axis: "yaw",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoRotateStepDeg);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(0, 0, 0, step);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y}
                                r={1.6}
                                fill="transparent"
                                stroke="rgba(251,191,36,0.6)"
                                strokeWidth={0.18}
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "luminaire",
                                    mode: "rotate",
                                    axis: "yaw",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "luminaire", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoRotateStepDeg);
                                  if (Number.isFinite(step)) {
                                    void nudgeLuminaireGizmo(0, 0, 0, -step);
                                  }
                                }}
                              />
                            </g>
                          );
                        })()
                      : null}
                    {selectedOpeningCenter
                      ? (() => {
                          const p = sceneProject(selectedOpeningCenter.x, selectedOpeningCenter.y, selectedOpeningCenter.z);
                          if (!p) {
                            return null;
                          }
                          return (
                            <g>
                              <rect x={p.x - 1.0} y={p.y - 1.0} width={2.0} height={2.0} fill="rgba(16,185,129,0.92)" />
                              <circle
                                cx={p.x + 3.8}
                                cy={p.y}
                                r={0.82}
                                fill="rgba(16,185,129,0.95)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "opening",
                                    mode: "move",
                                    axis: "x",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "opening", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void transformOpeningGizmo(step, 0, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x - 3.8}
                                cy={p.y}
                                r={0.82}
                                fill="rgba(16,185,129,0.95)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "opening",
                                    mode: "move",
                                    axis: "x",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "opening", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void transformOpeningGizmo(-step, 0, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y - 3.8}
                                r={0.82}
                                fill="rgba(16,185,129,0.95)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "opening",
                                    mode: "move",
                                    axis: "y",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "opening", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void transformOpeningGizmo(0, step, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y + 3.8}
                                r={0.82}
                                fill="rgba(16,185,129,0.95)"
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "opening",
                                    mode: "move",
                                    axis: "y",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "opening", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoMoveStepM);
                                  if (Number.isFinite(step)) {
                                    void transformOpeningGizmo(0, -step, 0, 0);
                                  }
                                }}
                              />
                              <circle
                                cx={p.x}
                                cy={p.y}
                                r={2.9}
                                fill="transparent"
                                stroke="rgba(34,197,94,0.9)"
                                strokeDasharray="1 0.7"
                                strokeWidth={0.18}
                                onPointerDown={(e) => {
                                  e.stopPropagation();
                                  gizmoDragRef.current = {
                                    active: true,
                                    pointerId: e.pointerId,
                                    target: "opening",
                                    mode: "rotate",
                                    axis: "yaw",
                                    lastClientX: e.clientX,
                                    lastClientY: e.clientY,
                                    accumDx: 0,
                                    accumDy: 0,
                                    accumYaw: 0,
                                  };
                                  patchState({ gizmoPreviewTarget: "opening", gizmoPreviewDx: 0, gizmoPreviewDy: 0, gizmoPreviewYawDeg: 0 });
                                }}
                                onClick={() => {
                                  const step = Number(state.gizmoRotateStepDeg);
                                  if (Number.isFinite(step)) {
                                    void transformOpeningGizmo(0, 0, 0, step);
                                  }
                                }}
                              />
                            </g>
                          );
                        })()
                      : null}
                    {state.sceneSelectActive ? (
                      <rect
                        x={Math.min(state.sceneSelectX0, state.sceneSelectX1)}
                        y={Math.min(state.sceneSelectY0, state.sceneSelectY1)}
                        width={Math.abs(state.sceneSelectX1 - state.sceneSelectX0)}
                        height={Math.abs(state.sceneSelectY1 - state.sceneSelectY0)}
                        fill="rgba(56,189,248,0.14)"
                        stroke="rgba(56,189,248,0.95)"
                        strokeDasharray="1.2 0.8"
                        strokeWidth={0.22}
                      />
                    ) : null}
                    {state.layerTablePoints &&
                    (state.sceneViewMode === "3d" ? sceneBounds3d : sceneBounds) &&
                    viewportPoints.length > 0
                      ? viewportPoints.map((p, i) => {
                          const m = sceneProject(p.x, p.y, 0);
                          if (!m) {
                            return null;
                          }
                          const isSelected = selectedPoint && Math.abs(selectedPoint.x - p.x) < 1e-9 && Math.abs(selectedPoint.y - p.y) < 1e-9;
                          return <circle key={`table-point-${i}`} cx={m.x} cy={m.y} r={isSelected ? 1.7 : 0.8} fill={isSelected ? "#60a5fa" : "rgba(148,163,184,0.8)"} />;
                        })
                      : null}
                    {state.sceneViewMode === "plan" &&
                    (!sceneBounds ||
                      (sceneRooms.length === 0 &&
                        sceneSurfaces.length === 0 &&
                        sceneOpenings.length === 0 &&
                        sceneLuminaires.length === 0 &&
                        sceneGrids.length === 0 &&
                        beamSpreadRows.length === 0)) &&
                    state.layerTablePoints &&
                    viewportPoints.length > 0 &&
                    viewportBounds
                      ? viewportPoints.map((p, i) => {
                          const spanX = Math.max(viewportBounds.maxX - viewportBounds.minX, 1e-9);
                          const spanY = Math.max(viewportBounds.maxY - viewportBounds.minY, 1e-9);
                          const px = 6 + ((p.x - viewportBounds.minX) / spanX) * 88;
                          const py = 64 - ((p.y - viewportBounds.minY) / spanY) * 58;
                          const isSelected = selectedPoint && Math.abs(selectedPoint.x - p.x) < 1e-9 && Math.abs(selectedPoint.y - p.y) < 1e-9;
                          return <circle key={`${p.label}-${i}`} cx={px} cy={py} r={isSelected ? 2.6 : 1.6} fill={isSelected ? "#60a5fa" : "#94a3b8"} />;
                        })
                      : null}
                  </svg>
                </div>
                <div className="space-y-2 text-xs text-muted">
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Scene: rooms {sceneRooms.length} / surfaces {sceneSurfaces.length} / openings {sceneOpenings.length} / luminaires{" "}
                    {sceneLuminaires.length} / beam spreads {beamSpreadRows.length}
                  </div>
                  {state.placementMode === "grid" ? (
                    <div className="rounded border border-blue-400/40 bg-blue-900/20 px-2 py-1 text-[11px] text-blue-100">
                      Click to set grid origin, then drag to set extent.
                    </div>
                  ) : null}
                  <div className="grid grid-cols-2 gap-1">
                    <input
                      value={state.gizmoMoveStepM}
                      onChange={(e) => patchState({ gizmoMoveStepM: e.target.value })}
                      placeholder="Move step m"
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    />
                    <input
                      value={state.gizmoRotateStepDeg}
                      onChange={(e) => patchState({ gizmoRotateStepDeg: e.target.value })}
                      placeholder="Rotate step deg"
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    <ToolbarButton onClick={() => void undoProjectChange()} disabled={state.designLoading || undoDepth <= 0} className="w-full">
                      Undo ({undoDepth})
                    </ToolbarButton>
                    <ToolbarButton onClick={() => void redoProjectChange()} disabled={state.designLoading || redoDepth <= 0} className="w-full">
                      Redo ({redoDepth})
                    </ToolbarButton>
                  </div>
                  <div className="grid grid-cols-5 gap-1">
                    <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-[11px] text-muted">
                      <input
                        type="checkbox"
                        checked={state.gizmoSnapEnabled}
                        onChange={(e) => patchState({ gizmoSnapEnabled: e.target.checked })}
                      />
                      Snap
                    </label>
                    <input
                      value={state.gizmoMoveSnapM}
                      onChange={(e) => patchState({ gizmoMoveSnapM: e.target.value })}
                      placeholder="Move snap m"
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    />
                    <input
                      value={state.gizmoAngleSnapDeg}
                      onChange={(e) => patchState({ gizmoAngleSnapDeg: e.target.value })}
                      placeholder="Angle snap deg"
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    />
                    <select
                      value={state.gizmoAxisLock}
                      onChange={(e) => patchState({ gizmoAxisLock: e.target.value as "none" | "x" | "y" })}
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    >
                      <option value="none">Axis free</option>
                      <option value="x">Lock X</option>
                      <option value="y">Lock Y</option>
                    </select>
                    <select
                      value={state.gizmoMoveFrame}
                      onChange={(e) => patchState({ gizmoMoveFrame: e.target.value as "world" | "local" })}
                      className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                    >
                      <option value="world">World frame</option>
                      <option value="local">Local frame</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    <ToolbarButton
                      onClick={() => patchState({ sceneViewMode: "plan" })}
                      className={`w-full ${state.sceneViewMode === "plan" ? "ring-1 ring-blue-400/50" : ""}`}
                    >
                      Plan
                    </ToolbarButton>
                    <ToolbarButton
                      onClick={() => patchState({ sceneViewMode: "3d" })}
                      className={`w-full ${state.sceneViewMode === "3d" ? "ring-1 ring-blue-400/50" : ""}`}
                    >
                      3D
                    </ToolbarButton>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    <ToolbarButton onClick={() => resetSceneView()} className="w-full">
                      Fit
                    </ToolbarButton>
                    <ToolbarButton
                      onClick={() =>
                        state.sceneViewMode === "plan"
                          ? patchState({ sceneZoom: clampZoom(state.sceneZoom * 1.12) })
                          : patchState({ sceneCamDistance: clampDistance(Number(state.sceneCamDistance) / 1.12).toFixed(4) })
                      }
                      className="w-full"
                    >
                      Zoom In
                    </ToolbarButton>
                    <ToolbarButton
                      onClick={() =>
                        state.sceneViewMode === "plan"
                          ? patchState({ sceneZoom: clampZoom(state.sceneZoom / 1.12) })
                          : patchState({ sceneCamDistance: clampDistance(Number(state.sceneCamDistance) * 1.12).toFixed(4) })
                      }
                      className="w-full"
                    >
                      Zoom Out
                    </ToolbarButton>
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-[11px]">
                      {state.sceneViewMode === "plan" ? `z=${state.sceneZoom.toFixed(2)}` : `d=${Number(state.sceneCamDistance).toFixed(2)}`}
                    </div>
                  </div>
                  {state.sceneViewMode === "3d" ? (
                    <div className="grid grid-cols-2 gap-1">
                      <input
                        value={state.sceneCamYawDeg}
                        onChange={(e) => patchState({ sceneCamYawDeg: e.target.value })}
                        placeholder="Yaw"
                        className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.sceneCamPitchDeg}
                        onChange={(e) => patchState({ sceneCamPitchDeg: e.target.value })}
                        placeholder="Pitch"
                        className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.sceneCamTargetX}
                        onChange={(e) => patchState({ sceneCamTargetX: e.target.value })}
                        placeholder="Target X"
                        className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.sceneCamTargetY}
                        onChange={(e) => patchState({ sceneCamTargetY: e.target.value })}
                        placeholder="Target Y"
                        className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-[11px] text-text outline-none"
                      />
                    </div>
                  ) : null}
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-[11px] text-muted">
                    <div className="mb-1 text-text">Heatmap</div>
                    <div className="mb-2 grid grid-cols-2 gap-1">
                      <ToolbarButton onClick={() => void loadFalseColorData()} className="w-full">
                        Load Heatmap
                      </ToolbarButton>
                      <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px]">
                        Grids: {state.falseColorData?.grids.length ?? 0}
                      </div>
                    </div>
                    <div className="mb-2 grid grid-cols-2 gap-1">
                      <ToolbarButton onClick={() => void loadBeamSpreadData()} className="w-full">
                        Load Beam Spread
                      </ToolbarButton>
                      <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px]">
                        Luminaires: {beamSpreadRows.length}
                      </div>
                    </div>
                    <label className="mb-1 block text-[11px] text-muted">
                      Opacity: {falseColorOpacity.toFixed(1)}
                      <input
                        type="range"
                        min="0.1"
                        max="1.0"
                        step="0.1"
                        value={state.falseColorOpacity}
                        onChange={(e) => patchState({ falseColorOpacity: e.target.value })}
                        className="w-full"
                      />
                    </label>
                    <label className="mb-1 flex items-center gap-2 rounded border border-border/60 bg-panel px-2 py-1 text-[11px]">
                      <input
                        type="checkbox"
                        checked={state.falseColorShowContours}
                        onChange={(e) => patchState({ falseColorShowContours: e.target.checked })}
                      />
                      Show Contours
                    </label>
                    <label className="flex items-center gap-2 rounded border border-border/60 bg-panel px-2 py-1 text-[11px]">
                      <input
                        type="checkbox"
                        checked={state.falseColorShowValues}
                        onChange={(e) => patchState({ falseColorShowValues: e.target.checked })}
                      />
                      Show Values
                    </label>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-[11px] text-muted">
                    <div className="mb-1 text-text">Transform Inspector</div>
                    <div className="mb-1">Luminaire ({state.aimLuminaireId || "none"})</div>
                    <div className="mb-1">
                      Current:{" "}
                      {selectedLuminairePoint
                        ? `x=${selectedLuminairePoint.x.toFixed(3)} y=${selectedLuminairePoint.y.toFixed(3)} z=${selectedLuminairePoint.z.toFixed(3)} yaw=${selectedLuminaireYawDisplayDeg.toFixed(2)}`
                        : "N/A"}
                    </div>
                    <div className="mb-1 grid grid-cols-4 gap-1">
                      <input
                        value={state.inspectorLumTargetX}
                        onChange={(e) => patchState({ inspectorLumTargetX: e.target.value })}
                        placeholder="X"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorLumTargetY}
                        onChange={(e) => patchState({ inspectorLumTargetY: e.target.value })}
                        placeholder="Y"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorLumTargetZ}
                        onChange={(e) => patchState({ inspectorLumTargetZ: e.target.value })}
                        placeholder="Z"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorLumTargetYaw}
                        onChange={(e) => patchState({ inspectorLumTargetYaw: e.target.value })}
                        placeholder="Yaw"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                    </div>
                    <ToolbarButton onClick={() => void applyLuminaireInspectorAbsolute()} className="mb-2 w-full">
                      Apply Luminaire Absolute
                    </ToolbarButton>
                    <div className="mb-1">Opening ({state.apertureOpeningId || "none"})</div>
                    <div className="mb-1">
                      Current:{" "}
                      {selectedOpeningCenter
                        ? `x=${selectedOpeningCenter.x.toFixed(3)} y=${selectedOpeningCenter.y.toFixed(3)} z=${selectedOpeningCenter.z.toFixed(3)} yaw=${selectedOpeningYawDisplayDeg.toFixed(2)}`
                        : "N/A"}
                    </div>
                    <div className="mb-1 grid grid-cols-4 gap-1">
                      <input
                        value={state.inspectorOpeningTargetX}
                        onChange={(e) => patchState({ inspectorOpeningTargetX: e.target.value })}
                        placeholder="X"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorOpeningTargetY}
                        onChange={(e) => patchState({ inspectorOpeningTargetY: e.target.value })}
                        placeholder="Y"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorOpeningTargetZ}
                        onChange={(e) => patchState({ inspectorOpeningTargetZ: e.target.value })}
                        placeholder="Z"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                      <input
                        value={state.inspectorOpeningTargetYaw}
                        onChange={(e) => patchState({ inspectorOpeningTargetYaw: e.target.value })}
                        placeholder="Yaw"
                        className="w-full rounded border border-border bg-panel px-1 py-1 text-[11px] text-text outline-none"
                      />
                    </div>
                    <ToolbarButton onClick={() => void applyOpeningInspectorAbsolute()} className="w-full">
                      Apply Opening Absolute
                    </ToolbarButton>
                  </div>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerRooms} onChange={(e) => patchState({ layerRooms: e.target.checked })} /> Rooms
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerSurfaces} onChange={(e) => patchState({ layerSurfaces: e.target.checked })} /> Surfaces
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerOpenings} onChange={(e) => patchState({ layerOpenings: e.target.checked })} /> Openings
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerGrids} onChange={(e) => patchState({ layerGrids: e.target.checked })} /> Grids
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerGridPoints} onChange={(e) => patchState({ layerGridPoints: e.target.checked })} /> Grid Points
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input
                      type="checkbox"
                      checked={state.layerFalseColor}
                      onChange={(e) => patchState({ layerFalseColor: e.target.checked })}
                    />{" "}
                    Heatmap
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerBeamSpread} onChange={(e) => patchState({ layerBeamSpread: e.target.checked })} /> Beam Spread
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input type="checkbox" checked={state.layerLuminaires} onChange={(e) => patchState({ layerLuminaires: e.target.checked })} /> Luminaires
                  </label>
                  <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    <input
                      type="checkbox"
                      checked={state.layerTablePoints}
                      onChange={(e) => patchState({ layerTablePoints: e.target.checked })}
                    />{" "}
                    Table Points
                  </label>
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
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Click geometry to bind IDs:
                    <br />
                    room -&gt; edit/array, surface -&gt; material, opening -&gt; aperture, luminaire -&gt; aim.
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    {state.sceneViewMode === "3d"
                      ? "3D controls: drag orbit, Alt+drag pan, wheel zoom, Shift+drag lasso."
                      : "Plan controls: drag pan, wheel zoom, Shift+drag lasso."}
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Gizmos: click red/blue/green handles to move selected luminaire/opening. Click ring to rotate.
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Drag handles for continuous transforms; release pointer to commit. Snap, axis lock, and local/world frame apply to preview and commit.
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    `Shift + drag` for rectangle selection:
                    <br />
                    surfaces -&gt; material set, luminaires -&gt; selection + aim target.
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                    Selected luminaires: {state.sceneSelectedLuminaireIdsCsv || "none"}
                  </div>
                  <ToolbarButton
                    onClick={() => patchState({ sceneSelectedLuminaireIdsCsv: "", materialSurfaceIdsCsv: "" })}
                    className="w-full"
                  >
                    Clear Scene Selection
                  </ToolbarButton>
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
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.projectPath}
                  onChange={(e) => patchState({ projectPath: e.target.value })}
                  placeholder="Project file path (.json)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void browseProjectPath()} disabled={state.projectLifecycleLoading}>
                  Browse
                </ToolbarButton>
                <input
                  value={state.projectName}
                  onChange={(e) => patchState({ projectName: e.target.value })}
                  placeholder="Project name (for init)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void chooseNewProjectPathAndInit()} disabled={state.projectLifecycleLoading}>
                  New...
                </ToolbarButton>
                <ToolbarButton onClick={() => void initProjectDocument()} disabled={state.projectLifecycleLoading}>
                  {state.projectLifecycleLoading ? "Working..." : "New"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void openProjectFromDialog()} disabled={state.projectLifecycleLoading}>
                  Open...
                </ToolbarButton>
                <ToolbarButton onClick={() => void openProjectDocument()} disabled={state.projectLifecycleLoading}>
                  Open
                </ToolbarButton>
                <ToolbarButton onClick={() => void saveProjectDocument()} disabled={state.projectLifecycleLoading || !state.projectDocDirty}>
                  Save
                </ToolbarButton>
                <ToolbarButton onClick={() => void saveProjectAsDialog()} disabled={state.projectLifecycleLoading}>
                  Save As...
                </ToolbarButton>
                <ToolbarButton onClick={() => void validateProjectDocument()} disabled={state.projectLifecycleLoading}>
                  Validate
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr]">
                <select
                  value={state.projectPath}
                  onChange={(e) => patchState({ projectPath: e.target.value })}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                >
                  <option value="">Recent projects...</option>
                  {state.recentProjects.map((path) => (
                    <option key={path} value={path}>
                      {path}
                    </option>
                  ))}
                </select>
                <ToolbarButton
                  onClick={() => {
                    const path = state.projectPath.trim();
                    if (path) {
                      void openProjectDocument(path);
                    }
                  }}
                  disabled={state.projectLifecycleLoading || !state.projectPath.trim()}
                >
                  Open Selected
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => {
                    patchState({ recentProjects: [] });
                    void persistRecentProjects([]);
                  }}
                  disabled={state.recentProjects.length === 0}
                >
                  Clear Recent
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
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
                <input
                  value={state.geomImportPath}
                  onChange={(e) => patchState({ geomImportPath: e.target.value })}
                  placeholder="Geometry file path (DXF/OBJ/GLTF/FBX/SKP/IFC/DWG)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void browseGeometryImportPath()} disabled={state.geomLoading}>
                  Browse
                </ToolbarButton>
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
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.photometryFilePath}
                  onChange={(e) => patchState({ photometryFilePath: e.target.value })}
                  placeholder="Photometry file path (.ies/.ldt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void browsePhotometryPath()} disabled={state.luminaireLoading}>
                  Browse
                </ToolbarButton>
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
                <ToolbarButton onClick={() => void verifyImportPhotometry()} disabled={state.photometryVerifyLoading}>
                  {state.photometryVerifyLoading ? "Verifying..." : "Verify Import File"}
                </ToolbarButton>
              </div>
              <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 p-2">
                <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
                  <input
                    value={state.photometryLibraryQuery}
                    onChange={(e) => patchState({ photometryLibraryQuery: e.target.value })}
                    placeholder="Search project photometry assets (id/path/hash/manufacturer/name)"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <input
                    value={state.selectedPhotometryAssetId}
                    onChange={(e) => patchState({ selectedPhotometryAssetId: e.target.value })}
                    placeholder="Selected asset id"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <ToolbarButton
                    onClick={() =>
                      patchState({
                        luminaireAssetId: state.selectedPhotometryAssetId.trim(),
                        arrayAssetId: state.selectedPhotometryAssetId.trim() || state.arrayAssetId,
                      })
                    }
                    disabled={!state.selectedPhotometryAssetId.trim()}
                  >
                    Use Selected Asset
                  </ToolbarButton>
                  <ToolbarButton onClick={() => void verifySelectedProjectPhotometry()} disabled={state.photometryVerifyLoading}>
                    {state.photometryVerifyLoading ? "Inspecting..." : "Inspect Selected Asset"}
                  </ToolbarButton>
                  <ToolbarButton onClick={() => void loadPolarDistribution()} disabled={state.polarPlotLoading}>
                    {state.polarPlotLoading ? "Loading..." : "Show Distribution"}
                  </ToolbarButton>
                </div>
                {filteredPhotometryRows.length === 0 ? (
                  <div className="rounded border border-border/60 bg-panel px-2 py-2 text-xs text-muted">No project photometry assets.</div>
                ) : (
                  <div className="max-h-44 overflow-auto rounded border border-border/60">
                    <table className="min-w-full text-xs">
                      <thead className="sticky top-0 bg-panel">
                        <tr>
                          <th className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">id</th>
                          <th className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">format</th>
                          <th className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">path</th>
                          <th className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">hash</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPhotometryRows.map((row, idx) => {
                          const id = String(row.id ?? "");
                          const selected = state.selectedPhotometryAssetId === id;
                          return (
                            <tr
                              key={`photometry-asset-${idx}-${id}`}
                              className={`cursor-pointer odd:bg-panelSoft/30 hover:bg-blue-900/20 ${selected ? "bg-blue-900/30 ring-1 ring-blue-400/40" : ""}`}
                              onClick={() => patchState({ selectedPhotometryAssetId: id })}
                            >
                              <td className="border-b border-border/50 px-2 py-1 text-text">{id}</td>
                              <td className="border-b border-border/50 px-2 py-1 text-text">{String(row.format ?? "")}</td>
                              <td className="border-b border-border/50 px-2 py-1 text-text">{String(row.path ?? "")}</td>
                              <td className="border-b border-border/50 px-2 py-1 text-text">{String(row.hash ?? "")}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
              {state.photometryVerifyError ? <div className="mb-2 text-xs text-rose-300">{state.photometryVerifyError}</div> : null}
              {state.polarPlotError ? <div className="mb-2 text-xs text-rose-300">{state.polarPlotError}</div> : null}
              {state.polarPlotData ? (
                <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 p-2">
                  <div className="mb-1 text-xs uppercase tracking-[0.12em] text-muted">Polar Distribution</div>
                  {(() => {
                    const size = 300;
                    const cx = 150;
                    const cy = 150;
                    const plotRadius = 120;
                    const maxCandela = Math.max(1e-9, Number(state.polarPlotData?.max_candela ?? 0));
                    const radialAngles = [0, 30, 60, 90, 120, 150, 180];
                    return (
                      <div className="rounded border border-border/60 bg-panel p-2">
                        <svg viewBox={`0 0 ${size} ${size}`} className="h-[300px] w-[300px] rounded border border-border/60 bg-panelSoft/50">
                          {[0.25, 0.5, 0.75, 1].map((f, idx) => (
                            <circle
                              key={`polar-ring-${idx}`}
                              cx={cx}
                              cy={cy}
                              r={plotRadius * f}
                              fill="none"
                              stroke="rgba(148,163,184,0.25)"
                              strokeWidth={0.8}
                            />
                          ))}
                          {radialAngles.map((g) => {
                            const t = (g * Math.PI) / 180;
                            const xr = cx + plotRadius * Math.sin(t);
                            const yr = cy + plotRadius * Math.cos(t);
                            const xl = cx - plotRadius * Math.sin(t);
                            const yl = cy + plotRadius * Math.cos(t);
                            return (
                              <g key={`polar-angle-${g}`}>
                                <line x1={cx} y1={cy} x2={xr} y2={yr} stroke="rgba(148,163,184,0.25)" strokeWidth={0.8} />
                                {g > 0 && g < 180 ? <line x1={cx} y1={cy} x2={xl} y2={yl} stroke="rgba(148,163,184,0.25)" strokeWidth={0.8} /> : null}
                                <text x={xr} y={yr - 4} textAnchor="middle" fontSize={9} fill="rgba(226,232,240,0.8)">
                                  {g}°
                                </text>
                              </g>
                            );
                          })}
                          {polarPlanes.map((plane, idx) => {
                            const color = String(plane.color ?? (idx === 0 ? "#2E86AB" : "#E94F37"));
                            const halfA = ((plane.half_a as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
                            const halfB = ((plane.half_b as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
                            const ga = ((halfA.gamma_deg as unknown[]) ?? []).map((v) => Number(v)).filter((v) => Number.isFinite(v));
                            const ca = ((halfA.candela as unknown[]) ?? []).map((v) => Number(v)).filter((v) => Number.isFinite(v));
                            const gb = ((halfB.gamma_deg as unknown[]) ?? []).map((v) => Number(v)).filter((v) => Number.isFinite(v));
                            const cb = ((halfB.candela as unknown[]) ?? []).map((v) => Number(v)).filter((v) => Number.isFinite(v));
                            const pointsA = ga.slice(0, Math.min(ga.length, ca.length)).map((g, i) => ({ gammaDeg: g, candela: ca[i] }));
                            const pointsB = gb.slice(0, Math.min(gb.length, cb.length)).map((g, i) => ({ gammaDeg: g, candela: cb[i] }));
                            const dA = polarHalfToSvgPath(pointsA, maxCandela, "right", cx, cy, plotRadius);
                            const dB = polarHalfToSvgPath(pointsB, maxCandela, "left", cx, cy, plotRadius);
                            return (
                              <g key={`polar-plane-${idx}`}>
                                {dA ? <path d={dA} fill="none" stroke={color} strokeWidth={2} /> : null}
                                {dB ? <path d={dB} fill="none" stroke={color} strokeWidth={2} /> : null}
                              </g>
                            );
                          })}
                        </svg>
                        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted">
                          {polarPlanes.map((plane, idx) => (
                            <div key={`polar-legend-${idx}`} className="flex items-center gap-1">
                              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: String(plane.color ?? "#94a3b8") }} />
                              <span>{String(plane.label ?? `Plane ${idx + 1}`)}</span>
                            </div>
                          ))}
                        </div>
                        <div className="mt-2 text-[11px] text-muted">
                          Total Flux: {Number(state.polarPlotData?.total_lumens ?? 0).toFixed(0)} lm | Beam:{" "}
                          {Number(state.polarPlotData?.beam_angle_deg ?? 0).toFixed(1)}° | Field:{" "}
                          {Number(state.polarPlotData?.field_angle_deg ?? 0).toFixed(1)}° | DFR:{" "}
                          {(Number(state.polarPlotData?.downward_flux_ratio ?? 0) * 100).toFixed(1)}%
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : null}
              {photometryVerifyRows.length > 0 ? (
                <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 p-2">
                  <div className="mb-1 text-xs uppercase tracking-[0.12em] text-muted">Photometry Verification</div>
                  <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-4">
                    <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px] text-muted">
                      Asset: {String(state.photometryVerifyResult?.asset_id ?? "N/A")}
                    </div>
                    <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px] text-muted">
                      Format: {String(state.photometryVerifyResult?.format ?? state.photometryVerifyResult?.asset_format ?? "N/A")}
                    </div>
                    <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px] text-muted">
                      Flux: {String((state.photometryVerifyResult?.luminous as Record<string, unknown> | undefined)?.flux_lm ?? "N/A")} lm
                    </div>
                    <div className="rounded border border-border/60 bg-panel px-2 py-1 text-[11px] text-muted">
                      Peak: {String((state.photometryVerifyResult?.candela_stats as Record<string, unknown> | undefined)?.max_cd ?? "N/A")} cd
                    </div>
                  </div>
                  <div className="max-h-32 overflow-auto rounded border border-border/60 bg-panel p-2">
                    <pre className="whitespace-pre-wrap text-[11px] text-muted">
                      {JSON.stringify(state.photometryVerifyResult, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : null}
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
              <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Quick Layout</div>
                <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr]">
                  <input
                    value={state.quickLayoutTargetLux}
                    onChange={(e) => patchState({ quickLayoutTargetLux: e.target.value })}
                    placeholder="Target lux"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <input
                    value={state.quickLayoutMaxRows}
                    onChange={(e) => patchState({ quickLayoutMaxRows: e.target.value })}
                    placeholder="Max rows"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <input
                    value={state.quickLayoutMaxCols}
                    onChange={(e) => patchState({ quickLayoutMaxCols: e.target.value })}
                    placeholder="Max cols"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <ToolbarButton onClick={() => void proposeQuickLayout()} disabled={state.quickLayoutLoading}>
                    {state.quickLayoutLoading ? "Working..." : "Calculate Layout"}
                  </ToolbarButton>
                  <ToolbarButton
                    onClick={() => void applyQuickLayout()}
                    disabled={state.quickLayoutLoading || !state.quickLayoutResult || !Array.isArray(state.quickLayoutResult.luminaires) || state.quickLayoutResult.luminaires.length === 0}
                  >
                    {state.quickLayoutLoading ? "Working..." : "Apply Layout"}
                  </ToolbarButton>
                </div>
                <div className="mb-2 rounded border border-border/60 bg-panel px-2 py-1 text-xs text-text">
                  {state.quickLayoutResult
                    ? `${state.quickLayoutResult.best.rows}×${state.quickLayoutResult.best.cols} = ${state.quickLayoutResult.best.fixture_count} luminaires | Est. ${state.quickLayoutResult.best.mean_lux.toFixed(1)} lux | U₀ = ${state.quickLayoutResult.best.uniformity.toFixed(3)}`
                    : "Run Calculate Layout to evaluate an optimized rectangular array."}
                </div>
                <label className="flex items-center gap-2 rounded border border-border/60 bg-panel px-2 py-1">
                  <input
                    type="checkbox"
                    checked={state.quickLayoutPreviewEnabled}
                    onChange={(e) => patchState({ quickLayoutPreviewEnabled: e.target.checked })}
                    disabled={!state.quickLayoutResult}
                  />
                  Preview in Viewport
                </label>
                {state.quickLayoutError ? <div className="mt-1 text-rose-300">{state.quickLayoutError}</div> : null}
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
              <details open>
                <summary className="cursor-pointer select-none text-xs uppercase tracking-[0.12em] text-muted">Luminaire Schedule</summary>
                <div className="mt-2 space-y-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2">
                    <div className="mb-1 text-[11px] text-text">Summary by Asset</div>
                    <div className="max-h-36 overflow-auto rounded border border-border/60">
                      <table className="w-full min-w-[640px] text-[11px] text-muted">
                        <thead className="bg-panel">
                          <tr>
                            <th className="px-2 py-1 text-left text-text">Tag</th>
                            <th className="px-2 py-1 text-right text-text">Quantity</th>
                            <th className="px-2 py-1 text-right text-text">Maintenance Factor</th>
                            <th className="px-2 py-1 text-right text-text">Flux Multiplier</th>
                            <th className="px-2 py-1 text-right text-text">Mounting Height (avg)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scheduleSummaryRows.map((row) => {
                            const selectedAll = row.luminaireIds.length > 0 && row.luminaireIds.every((id) => selectedLuminaireIdsSet.has(id));
                            return (
                              <tr
                                key={`schedule-summary-${row.tag}`}
                                className={`cursor-pointer border-t border-border/60 hover:bg-blue-900/20 ${selectedAll ? "bg-blue-900/30 ring-1 ring-blue-400/40" : ""}`}
                                onClick={() => selectLuminaireGroup(row.luminaireIds)}
                              >
                                <td className="px-2 py-1 text-text">{row.tag}</td>
                                <td className="px-2 py-1 text-right">{row.quantity}</td>
                                <td className="px-2 py-1 text-right">{row.avgMf.toFixed(2)}</td>
                                <td className="px-2 py-1 text-right">{row.avgMultiplier.toFixed(2)}</td>
                                <td className="px-2 py-1 text-right">{row.avgMountZ.toFixed(2)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                        <tfoot>
                          <tr className="border-t border-border bg-panel">
                            <td className="px-2 py-1 text-text">Total</td>
                            <td className="px-2 py-1 text-right text-text">{luminaireInstances.length}</td>
                            <td className="px-2 py-1 text-right text-text" colSpan={2}>
                              Connected Load
                            </td>
                            <td className="px-2 py-1 text-right text-text">
                              {totalConnectedLoadWatts === null ? "—" : `${totalConnectedLoadWatts.toFixed(1)} W`}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2">
                    <div className="mb-1 text-[11px] text-text">Instances</div>
                    <div className="max-h-44 overflow-auto rounded border border-border/60">
                      <table className="w-full min-w-[760px] text-[11px] text-muted">
                        <thead className="bg-panel">
                          <tr>
                            <th className="px-2 py-1 text-left text-text">ID</th>
                            <th className="px-2 py-1 text-left text-text">Name</th>
                            <th className="px-2 py-1 text-left text-text">Asset</th>
                            <th className="px-2 py-1 text-right text-text">X</th>
                            <th className="px-2 py-1 text-right text-text">Y</th>
                            <th className="px-2 py-1 text-right text-text">Z</th>
                            <th className="px-2 py-1 text-right text-text">Yaw</th>
                            <th className="px-2 py-1 text-right text-text">MF</th>
                          </tr>
                        </thead>
                        <tbody>
                          {luminaireInstances.map((lum) => {
                            const selected = selectedLuminaireIdsSet.has(lum.id);
                            return (
                              <tr
                                key={`schedule-instance-${lum.id}`}
                                ref={(node) => {
                                  luminaireInstanceRowRefs.current[lum.id] = node;
                                }}
                                className={`cursor-pointer border-t border-border/60 hover:bg-blue-900/20 ${selected ? "bg-blue-900/30 ring-1 ring-blue-400/40" : ""}`}
                                onClick={() => selectLuminaireInstance(lum)}
                              >
                                <td className="px-2 py-1 text-text">{lum.id}</td>
                                <td className="px-2 py-1">{lum.name || "—"}</td>
                                <td className="px-2 py-1">{lum.assetId}</td>
                                <td className="px-2 py-1 text-right">{lum.x.toFixed(3)}</td>
                                <td className="px-2 py-1 text-right">{lum.y.toFixed(3)}</td>
                                <td className="px-2 py-1 text-right">{lum.z.toFixed(3)}</td>
                                <td className="px-2 py-1 text-right">{lum.yawDeg.toFixed(2)}</td>
                                <td className="px-2 py-1 text-right">{lum.maintenanceFactor.toFixed(2)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                        <tfoot>
                          <tr className="border-t border-border bg-panel">
                            <td className="px-2 py-1 text-text">Total</td>
                            <td className="px-2 py-1 text-right text-text" colSpan={2}>
                              {luminaireInstances.length} instances
                            </td>
                            <td className="px-2 py-1 text-right text-text" colSpan={4}>
                              Connected Load
                            </td>
                            <td className="px-2 py-1 text-right text-text">
                              {totalConnectedLoadWatts === null ? "—" : `${totalConnectedLoadWatts.toFixed(1)} W`}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>
                  <div className={`rounded border px-2 py-1 text-xs ${liveEstimateTone}`}>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-semibold text-text">Live Estimate</span>
                      <span title="Estimated using lumen method. Run calculation for accurate results." className="cursor-help text-[11px] text-muted">
                        ℹ
                      </span>
                      {state.liveEstimateLoading ? (
                        <span>Estimating...</span>
                      ) : state.liveEstimate ? (
                        <>
                          <span>
                            Est. ~
                            {typeof state.liveEstimate.estimated_mean_lux === "number" && Number.isFinite(state.liveEstimate.estimated_mean_lux)
                              ? state.liveEstimate.estimated_mean_lux.toFixed(1)
                              : "—"}{" "}
                            lux
                          </span>
                          <span>
                            Uo ~
                            {typeof state.liveEstimate.estimated_uniformity === "number" && Number.isFinite(state.liveEstimate.estimated_uniformity)
                              ? state.liveEstimate.estimated_uniformity.toFixed(3)
                              : "—"}
                          </span>
                          <span>{state.liveEstimate.luminaire_count} luminaires</span>
                          <span>
                            RI=
                            {typeof state.liveEstimate.room_index === "number" && Number.isFinite(state.liveEstimate.room_index)
                              ? state.liveEstimate.room_index.toFixed(2)
                              : "—"}
                          </span>
                          <span className="text-muted">Confidence: {state.liveEstimate.confidence}</span>
                        </>
                      ) : (
                        <span>—</span>
                      )}
                    </div>
                    {state.liveEstimateError ? <div className="mt-1 text-[11px] text-rose-200">{state.liveEstimateError}</div> : null}
                  </div>
                </div>
              </details>
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Calculation Setup</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
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
                <div title={state.sceneViewMode === "3d" ? "Switch to plan view for click-to-place." : "Click in viewport to place grid by drag"}>
                  <ToolbarButton onClick={startGridPlacement} disabled={state.sceneViewMode === "3d"}>
                    Place Grid by Click
                  </ToolbarButton>
                </div>
                <ToolbarButton onClick={() => void addGrid()} disabled={state.calcSetupLoading}>
                  {state.calcSetupLoading ? "Working..." : "Add Grid"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_2fr]">
                <select
                  value={state.workplanePreset}
                  onChange={(e) => applyWorkplanePreset(e.target.value as "floor" | "desk" | "standing" | "custom")}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                >
                  <option value="floor">Floor (0.0m)</option>
                  <option value="desk">Desk Height (0.75m)</option>
                  <option value="standing">Standing (1.2m)</option>
                  <option value="custom">Custom...</option>
                </select>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Workplane Height Preset
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Elevation: {state.gridElevation} m
                </div>
              </div>
              <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Standard Profile</div>
                <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr]">
                  <select
                    value={state.selectedStandardActivityType}
                    onChange={(e) => patchState({ selectedStandardActivityType: e.target.value })}
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                    disabled={state.standardProfilesLoading}
                  >
                    <option value="">{state.standardProfilesLoading ? "Loading standards..." : "Select activity type..."}</option>
                    {standardProfilesByCategory.map(([category, rows]) => (
                      <optgroup key={`std-cat-${category}`} label={category}>
                        {rows.map((row) => (
                          <option key={`std-${row.activity_type}`} value={row.activity_type}>
                            {row.activity_type} - {row.description}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <input
                    value={state.selectedStandardProfileId}
                    onChange={(e) => patchState({ selectedStandardProfileId: e.target.value })}
                    placeholder="Profile id"
                    className="w-full rounded border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                  />
                  <ToolbarButton onClick={() => void applyStandardProfile()} disabled={state.calcSetupLoading || !selectedStandardProfile}>
                    {state.calcSetupLoading ? "Working..." : "Apply to Project"}
                  </ToolbarButton>
                </div>
                <div className="mb-1 rounded border border-border/60 bg-panel px-2 py-1 text-xs text-text">
                  {selectedStandardProfile
                    ? `Em ≥ ${selectedStandardProfile.maintained_illuminance_lux} lux | Uo ≥ ${selectedStandardProfile.uniformity_min} | UGR ≤ ${selectedStandardProfile.ugr_max} | CRI ≥ ${selectedStandardProfile.cri_min}`
                    : "Select a profile to view requirements."}
                </div>
                <div className="flex items-center gap-2">
                  <ToolbarButton onClick={() => void loadStandardProfiles()} disabled={state.standardProfilesLoading}>
                    {state.standardProfilesLoading ? "Refreshing..." : "Refresh Profiles"}
                  </ToolbarButton>
                  <span>Profiles: {state.standardProfiles.length}</span>
                </div>
                {state.standardProfilesError ? <div className="mt-1 text-rose-300">{state.standardProfilesError}</div> : null}
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
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr_1fr_1fr_1fr_1fr]">
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
                <ToolbarButton onClick={() => void browseExportOutputPath()} disabled={state.exportLoading}>
                  Browse
                </ToolbarButton>
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
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_3fr]">
                <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={state.agentApprovalApplyDiff}
                    onChange={(e) => patchState({ agentApprovalApplyDiff: e.target.checked })}
                  />
                  approve `apply_diff`
                </label>
                <label className="flex items-center gap-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={state.agentApprovalRunJob}
                    onChange={(e) => patchState({ agentApprovalRunJob: e.target.checked })}
                  />
                  approve `run_job`
                </label>
                <input
                  value={state.agentSelectedOptionIndex}
                  onChange={(e) => patchState({ agentSelectedOptionIndex: e.target.value })}
                  placeholder="selected_option_index"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Agent loop: edit intent/approvals and rerun to iterate on previous result.
                </div>
              </div>
              {state.agentError ? <div className="mb-2 text-xs text-rose-300">{state.agentError}</div> : null}
              {state.agentResponse ? (
                <div className="space-y-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                    Plan: {(state.agentResponse.plan as string) ?? "N/A"}
                  </div>
                  <div className="grid grid-cols-1 gap-2 xl:grid-cols-4">
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                      Success: {String((state.agentResponse.ok as boolean | undefined) ?? false)}
                    </div>
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                      Actions: {String(((state.agentResponse.actions as unknown[]) ?? []).length)}
                    </div>
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                      Warnings: {String(((state.agentResponse.warnings as unknown[]) ?? []).length)}
                    </div>
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                      Errors: {String(((state.agentResponse.errors as unknown[]) ?? []).length)}
                    </div>
                  </div>
                  <DataTable title="Agent Actions" rows={agentActionRows} />
                  <DataTable title="Agent Diff Preview" rows={agentDiffPreviewRows} />
                  <DataTable title="Agent Warnings" rows={agentWarningRows} />
                  <DataTable title="Agent Errors" rows={agentErrorRows} />
                  <DataTable title="Agent Response Paths" rows={agentResponseRows} />
                </div>
              ) : null}
              {state.agentRunHistory.length > 0 ? (
                <div className="mt-2 space-y-2">
                  <DataTable title="Agent Run History" rows={agentHistoryRows} />
                  <div className="max-h-32 space-y-1 overflow-auto rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    {state.agentRunHistory.slice(0, 8).map((r) => (
                      <div key={`${r.atUnixMs}-${r.intent}`} className="flex items-center gap-2">
                        <span className="truncate text-text">{new Date(r.atUnixMs).toLocaleTimeString()} - {r.intent}</span>
                        <ToolbarButton
                          onClick={() => patchState({ agentIntent: r.intent, agentApprovalsJson: r.approvalsJson })}
                          className="ml-auto"
                        >
                          Reuse
                        </ToolbarButton>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Materials, Variants, Optimization</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-3">
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Rooms: {roomIds.length > 0 ? roomIds.join(", ") : "none"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Surfaces: {surfaceIds.length > 0 ? surfaceIds.join(", ") : "none"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Openings: {openingIds.length > 0 ? openingIds.join(", ") : "none"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Luminaires: {luminaireIds.length > 0 ? luminaireIds.join(", ") : "none"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Materials: {materialIds.length > 0 ? materialIds.join(", ") : "none"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Assets: {assetIds.length > 0 ? assetIds.join(", ") : "none"}
                </div>
              </div>

              <div className="mb-1 text-[11px] text-muted">Edit room + daylight aperture + escape route</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.editRoomId}
                  onChange={(e) => patchState({ editRoomId: e.target.value })}
                  placeholder={roomIds.length > 0 ? `Room id (${roomIds[0]})` : "Room id"}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomName}
                  onChange={(e) => patchState({ editRoomName: e.target.value })}
                  placeholder="Room name (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomWidth}
                  onChange={(e) => patchState({ editRoomWidth: e.target.value })}
                  placeholder="Width (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomLength}
                  onChange={(e) => patchState({ editRoomLength: e.target.value })}
                  placeholder="Length (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomHeight}
                  onChange={(e) => patchState({ editRoomHeight: e.target.value })}
                  placeholder="Height (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomOriginX}
                  onChange={(e) => patchState({ editRoomOriginX: e.target.value })}
                  placeholder="Origin X (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomOriginY}
                  onChange={(e) => patchState({ editRoomOriginY: e.target.value })}
                  placeholder="Origin Y (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.editRoomOriginZ}
                  onChange={(e) => patchState({ editRoomOriginZ: e.target.value })}
                  placeholder="Origin Z (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void editRoom()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Edit Room"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr]">
                <input
                  value={state.apertureOpeningId}
                  onChange={(e) => patchState({ apertureOpeningId: e.target.value })}
                  placeholder={openingIds.length > 0 ? `Opening id (${openingIds[0]})` : "Opening id"}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.apertureVt}
                  onChange={(e) => patchState({ apertureVt: e.target.value })}
                  placeholder="Visible transmittance (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void setDaylightAperture()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Set Daylight Aperture"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.escapeRouteId}
                  onChange={(e) => patchState({ escapeRouteId: e.target.value })}
                  placeholder="Route id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.escapeRoutePolylineCsv}
                  onChange={(e) => patchState({ escapeRoutePolylineCsv: e.target.value })}
                  placeholder="Polyline x,y,z;x,y,z;..."
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.escapeRouteWidthM}
                  onChange={(e) => patchState({ escapeRouteWidthM: e.target.value })}
                  placeholder="Width"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.escapeRouteSpacingM}
                  onChange={(e) => patchState({ escapeRouteSpacingM: e.target.value })}
                  placeholder="Spacing"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.escapeRouteHeightM}
                  onChange={(e) => patchState({ escapeRouteHeightM: e.target.value })}
                  placeholder="Height"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.escapeRouteEndMarginM}
                  onChange={(e) => patchState({ escapeRouteEndMarginM: e.target.value })}
                  placeholder="End margin"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void addEscapeRoute()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Add Escape Route"}
                </ToolbarButton>
              </div>

              <div className="mb-1 text-[11px] text-muted">Luminaire arrays + aiming</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.arrayRoomId}
                  onChange={(e) => patchState({ arrayRoomId: e.target.value })}
                  placeholder={roomIds.length > 0 ? `Room id (${roomIds[0]})` : "Room id"}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.arrayAssetId}
                  onChange={(e) => patchState({ arrayAssetId: e.target.value })}
                  placeholder={assetIds.length > 0 ? `Asset id (${assetIds[0]})` : "Asset id"}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.arrayRows}
                  onChange={(e) => patchState({ arrayRows: e.target.value })}
                  placeholder="Rows"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.arrayCols}
                  onChange={(e) => patchState({ arrayCols: e.target.value })}
                  placeholder="Cols"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.arrayMarginM}
                  onChange={(e) => patchState({ arrayMarginM: e.target.value })}
                  placeholder="Margin m"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.arrayMountHeightM}
                  onChange={(e) => patchState({ arrayMountHeightM: e.target.value })}
                  placeholder="Mount height m"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void arrayLuminaires()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Array Luminaires"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_1fr]">
                <input
                  value={state.aimLuminaireId}
                  onChange={(e) => patchState({ aimLuminaireId: e.target.value })}
                  placeholder={luminaireIds.length > 0 ? `Luminaire id (${luminaireIds[0]})` : "Luminaire id"}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.aimYawDeg}
                  onChange={(e) => patchState({ aimYawDeg: e.target.value })}
                  placeholder="Yaw deg"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void aimLuminaire()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Aim Luminaire"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr]">
                <input
                  value={state.sceneSelectedLuminaireIdsCsv}
                  onChange={(e) => patchState({ sceneSelectedLuminaireIdsCsv: e.target.value })}
                  placeholder="Selected luminaires CSV (from lasso or manual)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.batchYawDeg}
                  onChange={(e) => patchState({ batchYawDeg: e.target.value })}
                  placeholder="Batch yaw (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.batchMaintenanceFactor}
                  onChange={(e) => patchState({ batchMaintenanceFactor: e.target.value })}
                  placeholder="Batch maintenance (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.batchFluxMultiplier}
                  onChange={(e) => patchState({ batchFluxMultiplier: e.target.value })}
                  placeholder="Batch multiplier (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.batchTiltDeg}
                  onChange={(e) => patchState({ batchTiltDeg: e.target.value })}
                  placeholder="Batch tilt (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void batchUpdateSelectedLuminaires()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Batch Update"}
                </ToolbarButton>
              </div>

              <div className="mb-1 text-[11px] text-muted">Assign material to surfaces</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr]">
                <input
                  value={state.materialIdInput}
                  onChange={(e) => patchState({ materialIdInput: e.target.value })}
                  placeholder="Material id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.materialSurfaceIdsCsv}
                  onChange={(e) => patchState({ materialSurfaceIdsCsv: e.target.value })}
                  placeholder="Surface ids CSV (surface_1,surface_2,...)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void assignMaterial()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Assign Material"}
                </ToolbarButton>
              </div>

              <div className="mb-1 text-[11px] text-muted">Add project variant</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr_2fr_1fr]">
                <input
                  value={state.variantIdInput}
                  onChange={(e) => patchState({ variantIdInput: e.target.value })}
                  placeholder="Variant id"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.variantNameInput}
                  onChange={(e) => patchState({ variantNameInput: e.target.value })}
                  placeholder="Variant name"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.variantDescriptionInput}
                  onChange={(e) => patchState({ variantDescriptionInput: e.target.value })}
                  placeholder="Description (optional)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void addVariant()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Add Variant"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[3fr_1fr]">
                <input
                  value={state.variantDiffOpsJson}
                  onChange={(e) => patchState({ variantDiffOpsJson: e.target.value })}
                  placeholder='Variant diff ops JSON array (e.g. [{"op":"update","kind":"job","id":"job_1","payload":{"seed":1}}])'
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 font-mono text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void compareVariants()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Compare Variants"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr]">
                <input
                  value={state.variantCompareJobId}
                  onChange={(e) => patchState({ variantCompareJobId: e.target.value })}
                  placeholder={`Job id (default: ${state.selectedJobId || "selected"})`}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.variantCompareIdsCsv}
                  onChange={(e) => patchState({ variantCompareIdsCsv: e.target.value })}
                  placeholder="Variant ids CSV"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.variantCompareBaselineId}
                  onChange={(e) => patchState({ variantCompareBaselineId: e.target.value })}
                  placeholder="Baseline variant id (opt)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
              </div>

              <div className="mb-1 text-[11px] text-muted">Optimization search and apply</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_2fr_1fr_1fr]">
                <input
                  value={state.optimizationJobId}
                  onChange={(e) => patchState({ optimizationJobId: e.target.value })}
                  placeholder={`Job id (default: ${state.selectedJobId || "selected"})`}
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <input
                  value={state.optimizationConstraintsJson}
                  onChange={(e) => patchState({ optimizationConstraintsJson: e.target.value })}
                  placeholder='Constraints JSON (e.g. {"target_lux":500,"uniformity_min":0.4,"ugr_max":19})'
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 font-mono text-xs text-text outline-none"
                />
                <input
                  value={state.optimizationTopN}
                  onChange={(e) => patchState({ optimizationTopN: e.target.value })}
                  placeholder="Top N"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none"
                />
                <ToolbarButton onClick={() => void proposeOptimizations()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Propose Options"}
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[1fr_1fr]">
                <ToolbarButton onClick={() => void applySelectedOptimizationOption()} disabled={state.designLoading}>
                  {state.designLoading ? "Working..." : "Apply Selected Option"}
                </ToolbarButton>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Select a row from `Optimization Options` first.
                </div>
              </div>
              {state.designError ? <div className="mb-2 text-xs text-rose-300">{state.designError}</div> : null}
              {state.designMessage ? (
                <div className="mb-2 rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">{state.designMessage}</div>
              ) : null}
              {variantCompareRows.length > 0 ? <DataTable title="Variant Compare Rows" rows={variantCompareRows} /> : null}
              {optimizationOptionsRows.length > 0 ? (
                <DataTable
                  title="Optimization Options"
                  rows={optimizationOptionsRows}
                  onSelectRow={selectRow}
                  selectedTableTitle={state.selectedTableTitle}
                  selectedRowIndex={state.selectedRowIndex}
                />
              ) : null}
              {state.designResult ? <DataTable title="Design Operation Result Paths" rows={designResultRows} /> : null}
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
                {state.complianceDetailedLoading ? (
                  <div className="text-xs text-muted">Evaluating detailed compliance...</div>
                ) : state.complianceDetailedError ? (
                  <div className="rounded border border-amber-500/40 bg-amber-950/25 p-2 text-xs text-amber-100">
                    {state.complianceDetailedError}
                  </div>
                ) : state.complianceDetailed?.overall_status === "NO_PROFILE" ? (
                  <div className="rounded border border-amber-500/40 bg-amber-950/25 p-2 text-xs text-amber-100">
                    No compliance profile set. Select a standard in Calc Setup.
                  </div>
                ) : state.complianceDetailed ? (
                  <div className="space-y-2">
                    <div className={`rounded border px-2 py-1 text-xs font-semibold ${complianceBannerClass}`}>
                      <span className={complianceTone}>{complianceOverallStatus === "PASS" ? "COMPLIANT" : "NON-COMPLIANT"}</span>
                      {" • "}
                      {state.complianceDetailed.profile_name ?? "Compliance Profile"}
                      {state.complianceDetailed.standard ? ` (${state.complianceDetailed.standard})` : ""}
                    </div>
                    {(state.complianceDetailed.checks ?? []).map((check, idx) => {
                      const hasRequired = typeof check.required === "number" && Number.isFinite(check.required);
                      const hasActual = typeof check.actual === "number" && Number.isFinite(check.actual);
                      const ratio = hasRequired && hasActual && check.required !== 0 ? Math.min(check.actual / check.required, 1.5) : 0;
                      const widthPercent = Math.max(0, ratio * 100);
                      const pass = check.status === "PASS";
                      const fail = check.status === "FAIL";
                      return (
                        <div key={`${check.metric}-${idx}`} className="rounded border border-border/70 bg-panelSoft/40 p-2">
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <div className="font-semibold text-text">{check.metric}</div>
                            <div className={pass ? "text-emerald-300" : fail ? "text-rose-300" : "text-amber-200"}>{check.status}</div>
                          </div>
                          <div className="relative mt-1 h-2 overflow-hidden rounded bg-panel">
                            <div className="absolute inset-y-0 left-[66.666%] w-px bg-border" />
                            {check.direction === "<=" ? (
                              <div
                                className={pass ? "absolute right-0 top-0 h-full bg-emerald-500/70" : "absolute right-0 top-0 h-full bg-rose-500/70"}
                                style={{ width: `${widthPercent}%` }}
                              />
                            ) : (
                              <div
                                className={pass ? "absolute left-0 top-0 h-full bg-emerald-500/70" : "absolute left-0 top-0 h-full bg-rose-500/70"}
                                style={{ width: `${widthPercent}%` }}
                              />
                            )}
                          </div>
                          <div className="mt-1 grid grid-cols-2 gap-2 text-[11px] text-muted">
                            <div>
                              Actual: {hasActual ? check.actual.toFixed(2) : "N/A"}
                              {check.unit ? ` ${check.unit}` : ""}
                            </div>
                            <div>
                              Required: {hasRequired ? check.required.toFixed(2) : "N/A"}
                              {check.unit ? ` ${check.unit}` : ""}
                              {` (${check.direction})`}
                            </div>
                          </div>
                          <div className={fail ? "mt-1 text-[11px] text-rose-200" : "mt-1 text-[11px] text-emerald-200"}>
                            Delta:{" "}
                            {typeof check.delta === "number" && Number.isFinite(check.delta)
                              ? `${check.delta.toFixed(2)}${check.unit ? ` ${check.unit}` : ""}`
                              : "N/A"}
                            {typeof check.delta_percent === "number" && Number.isFinite(check.delta_percent)
                              ? ` (${check.delta_percent.toFixed(1)}%)`
                              : ""}
                          </div>
                          {fail && check.suggestion ? <div className="mt-1 text-[11px] text-muted">{check.suggestion}</div> : null}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <ul className="mt-2 space-y-1 text-xs text-muted">
                    {(model?.compliance.reasons ?? []).length > 0 ? (
                      (model?.compliance.reasons ?? []).map((reason) => <li key={reason}>{reason}</li>)
                    ) : (
                      <li>No compliance reasons reported.</li>
                    )}
                  </ul>
                )}
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
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Artifact Preview</div>
              {artifacts.artifactBinary ? (
                <div className="text-xs text-muted">
                  <div className="mb-2">
                    {artifacts.artifactBinary.path} ({artifacts.artifactBinary.sizeBytes} bytes){artifacts.artifactBinary.truncated ? " [truncated]" : ""}{" "}
                    / {artifacts.artifactBinary.mimeType}
                  </div>
                  {artifacts.artifactBinary.truncated ? (
                    <div className="mb-2 rounded border border-amber-500/40 bg-amber-950/25 px-2 py-1 text-amber-100">
                      Preview may be incomplete because the artifact exceeded the inline preview byte limit.
                    </div>
                  ) : null}
                  {artifacts.artifactBinary.mimeType.startsWith("image/") ? (
                    <img
                      src={`data:${artifacts.artifactBinary.mimeType};base64,${artifacts.artifactBinary.dataBase64}`}
                      alt="Artifact preview"
                      className="max-h-[420px] rounded border border-border/60 bg-panelSoft/50"
                    />
                  ) : artifacts.artifactBinary.mimeType === "application/pdf" ? (
                    <iframe
                      src={artifacts.artifactPreviewUrl || `data:${artifacts.artifactBinary.mimeType};base64,${artifacts.artifactBinary.dataBase64}`}
                      title="Artifact PDF preview"
                      className="h-[640px] w-full rounded border border-border/60 bg-panelSoft/50"
                    />
                  ) : (
                    <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1">
                      Selected artifact is not a supported inline preview type.
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
