type JsonRecord = Record<string, unknown>;

export interface DesktopResultBundle {
  sourceDir: string;
  result: unknown;
  tables: unknown;
  results: unknown;
  warnings: string[];
}

export interface SummaryMetrics {
  meanLux?: number;
  minLux?: number;
  maxLux?: number;
  uniformityRatio?: number;
  highestUgr?: number;
}

export interface ComplianceView {
  status: string;
  reasons: string[];
}

export interface DesktopViewModel {
  sourceDir: string;
  contractVersion: string;
  jobType: string;
  backendName: string;
  solverVersion: string;
  summary: SummaryMetrics;
  warnings: string[];
  compliance: ComplianceView;
  tableCounts: {
    grids: number;
    verticalPlanes: number;
    pointSets: number;
  };
  tables: {
    grids: JsonRecord[];
    verticalPlanes: JsonRecord[];
    pointSets: JsonRecord[];
  };
  zoneMetrics: JsonRecord[];
  indoorPlanes: JsonRecord[];
  contractIssues: string[];
  raw: {
    result: JsonRecord;
    tables: JsonRecord;
    results: JsonRecord;
  };
  radiosity: {
    available: boolean;
    converged?: boolean;
    iterations?: number;
    stopReason?: string;
    residuals: number[];
    solverStatus: JsonRecord | null;
    energy: JsonRecord | null;
  };
  ugr: {
    available: boolean;
    worstCase?: number;
    views: JsonRecord[];
    debug: JsonRecord | null;
  };
  roadway: {
    available: boolean;
    roadClass?: string;
    roadwayProfile: JsonRecord | null;
    roadway: JsonRecord | null;
    observerGlareViews: JsonRecord[];
  };
}

function asRecord(value: unknown): JsonRecord | null {
  return value !== null && typeof value === "object" ? (value as JsonRecord) : null;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((x): x is string => typeof x === "string");
}

function asRecordList(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((row) => asRecord(row)).filter((row): row is JsonRecord => row !== null);
}

function extractIndoorPlanes(summary: JsonRecord | null): JsonRecord[] {
  const planesPayload = asRecord(summary?.indoor_planes);
  if (!planesPayload) {
    return [];
  }
  const rows: JsonRecord[] = [];
  for (const [planeId, payload] of Object.entries(planesPayload)) {
    const rec = asRecord(payload);
    if (!rec) {
      continue;
    }
    rows.push({
      id: planeId,
      name: asString(rec.name) ?? planeId,
      mean_lux: asNumber(rec.mean_lux),
      min_lux: asNumber(rec.min_lux),
      max_lux: asNumber(rec.max_lux),
      uniformity_ratio: asNumber(rec.uniformity_ratio),
      point_count: asNumber(rec.point_count),
      plane_type: asString(rec.type),
    });
  }
  return rows;
}

function extractWarningCodes(warningsPayload: unknown): string[] {
  if (!Array.isArray(warningsPayload)) {
    return [];
  }
  const out: string[] = [];
  for (const item of warningsPayload) {
    const rec = asRecord(item);
    if (!rec) {
      continue;
    }
    const code = asString(rec.code);
    const message = asString(rec.message);
    if (code && message) {
      out.push(`${code}: ${message}`);
    } else if (code) {
      out.push(code);
    } else if (message) {
      out.push(message);
    }
  }
  return out;
}

function extractCompliance(summary: JsonRecord | null): ComplianceView {
  const complianceRaw = summary?.compliance;
  const compliance = asRecord(complianceRaw);
  if (!compliance) {
    return { status: "N/A", reasons: [] };
  }
  const status = asString(compliance.status) ?? "UNKNOWN";
  const reasons = asStringList(compliance.reasons);
  return { status, reasons };
}

function assertRequiredRecord(value: unknown, label: string): JsonRecord {
  const rec = asRecord(value);
  if (!rec) {
    throw new Error(`Desktop contract violation: missing or invalid ${label}.`);
  }
  return rec;
}

export function buildDesktopViewModel(bundle: DesktopResultBundle): DesktopViewModel {
  const result = assertRequiredRecord(bundle.result, "result.json");
  const summary = assertRequiredRecord(result.summary, "result.summary");
  const contractVersion = asString(result.contract_version);
  if (!contractVersion) {
    throw new Error("Desktop contract violation: result.contract_version is required.");
  }

  const tables = asRecord(bundle.tables) ?? {};
  const results = asRecord(bundle.results) ?? {};
  const job = asRecord(result.job);
  const backend = asRecord(result.backend);
  const solver = asRecord(result.solver);
  const gridRows = asRecordList(tables?.grids);
  const planeRows = asRecordList(tables?.vertical_planes);
  const pointRows = asRecordList(tables?.point_sets);
  const summaryZoneRows = asRecordList(summary?.zone_metrics);
  const tableZoneRows = asRecordList(tables?.zones);
  const zoneMetrics = summaryZoneRows.length > 0 ? summaryZoneRows : tableZoneRows;
  const indoorPlanes = extractIndoorPlanes(summary);
  const contractIssues: string[] = [];
  if (contractVersion !== "solver_result_v1") {
    contractIssues.push(`Unsupported contract version: ${contractVersion}`);
  }
  if (!asString(job?.type)) {
    contractIssues.push("Missing job.type in result payload");
  }
  if (!asString(backend?.name)) {
    contractIssues.push("Missing backend.name in result payload");
  }

  const warnings: string[] = [];
  warnings.push(...bundle.warnings);
  warnings.push(...asStringList(asRecord(result.photometry_verification)?.warnings));
  warnings.push(...extractWarningCodes(result.photometry_warnings));
  warnings.push(...extractWarningCodes(result.near_field_warnings));
  warnings.push(...asStringList(asRecord(summary.solver_status)?.warnings));

  const compliance = extractCompliance(summary);
  for (const reason of compliance.reasons) {
    warnings.push(`compliance: ${reason}`);
  }

  const residuals = Array.isArray(summary.residuals)
    ? summary.residuals.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
    : [];
  const solverStatus = asRecord(summary.solver_status);
  const energy = asRecord(summary.energy);
  const radiosityAvailable =
    job?.type === "radiosity" || residuals.length > 0 || solverStatus !== null || energy !== null;

  const ugrViews = asRecordList(summary.ugr_views);
  const ugrDebug = asRecord(summary.ugr_debug);
  const ugrWorstCase = asNumber(summary.ugr_worst_case) ?? asNumber(summary.highest_ugr);
  const ugrAvailable = typeof ugrWorstCase === "number" || ugrViews.length > 0 || ugrDebug !== null;

  const roadwayProfile = asRecord(summary.roadway_profile);
  const roadway = asRecord(summary.roadway);
  const observerGlareViews = asRecordList(summary.observer_glare_views);
  const roadwayAvailable = job?.type === "roadway" || roadwayProfile !== null || roadway !== null || observerGlareViews.length > 0;

  return {
    sourceDir: bundle.sourceDir,
    contractVersion,
    jobType: asString(job?.type) ?? "unknown",
    backendName: asString(backend?.name) ?? "unknown",
    solverVersion: asString(solver?.package_version) ?? "unknown",
    summary: {
      meanLux: asNumber(summary?.mean_lux) ?? asNumber(summary?.avg_illuminance),
      minLux: asNumber(summary.min_lux),
      maxLux: asNumber(summary.max_lux),
      uniformityRatio: asNumber(summary.uniformity_ratio),
      highestUgr: asNumber(summary.highest_ugr) ?? asNumber(summary.ugr_worst_case),
    },
    warnings: Array.from(new Set(warnings)),
    compliance,
    tableCounts: {
      grids: gridRows.length,
      verticalPlanes: planeRows.length,
      pointSets: pointRows.length,
    },
    tables: {
      grids: gridRows,
      verticalPlanes: planeRows,
      pointSets: pointRows,
    },
    zoneMetrics,
    indoorPlanes,
    contractIssues,
    raw: { result, tables, results },
    radiosity: {
      available: radiosityAvailable,
      converged: asBoolean(summary.converged),
      iterations: asNumber(summary.iterations),
      stopReason: asString(summary.stop_reason),
      residuals,
      solverStatus,
      energy,
    },
    ugr: {
      available: ugrAvailable,
      worstCase: ugrWorstCase,
      views: ugrViews,
      debug: ugrDebug,
    },
    roadway: {
      available: roadwayAvailable,
      roadClass: asString(summary.road_class),
      roadwayProfile,
      roadway,
      observerGlareViews,
    },
  };
}
