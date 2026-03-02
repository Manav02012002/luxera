type JsonRecord = Record<string, unknown>;

export interface DesktopResultBundle {
  sourceDir: string;
  result: unknown;
  tables: unknown;
  results: unknown;
  roadSummary: unknown;
  roadwaySubmission: unknown;
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
    roadSummary: JsonRecord;
    roadwaySubmission: JsonRecord;
  };
  roadwaySubmission: {
    available: boolean;
    source: string;
    title?: string;
    status?: string;
    profile: JsonRecord | null;
    overall: JsonRecord | null;
    checks: JsonRecord[];
    validationIssues: string[];
  };
  engines: {
    available: boolean;
    summaries: JsonRecord[];
  };
  radiosity: {
    available: boolean;
    converged?: boolean;
    iterations?: number;
    stopReason?: string;
    residuals: number[];
    energyBalanceHistory: number[];
    solverStatus: JsonRecord | null;
    energy: JsonRecord | null;
    diagnostics: JsonRecord | null;
    residualThreshold?: number;
    residualBelowThreshold?: boolean;
    residualNonincreasing?: boolean;
  };
  ugr: {
    available: boolean;
    worstCase?: number;
    views: JsonRecord[];
    debug: JsonRecord | null;
    debugTopContributors: JsonRecord[];
    viewTopContributors: JsonRecord[];
  };
  roadway: {
    available: boolean;
    roadClass?: string;
    roadwayProfile: JsonRecord | null;
    roadway: JsonRecord | null;
    compliance: JsonRecord | null;
    laneMetrics: JsonRecord[];
    observerLuminanceViews: JsonRecord[];
    tiObservers: JsonRecord[];
    observerGlareViews: JsonRecord[];
    luminanceModel: JsonRecord | null;
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

function extractEngineSummary(results: JsonRecord, jobId: string | undefined, jobType: string | undefined): JsonRecord | null {
  const engines = asRecord(results.engines);
  if (!engines) {
    return null;
  }

  let byJobId: JsonRecord | null = null;
  let byJobType: JsonRecord | null = null;
  let firstSummary: JsonRecord | null = null;
  for (const payload of Object.values(engines)) {
    const engine = asRecord(payload);
    const summary = asRecord(engine?.summary);
    if (!summary) {
      continue;
    }
    if (!firstSummary) {
      firstSummary = summary;
    }
    if (!byJobId && jobId && asString(engine?.job_id) === jobId) {
      byJobId = summary;
    }
    if (!byJobType && jobType && asString(engine?.job_type) === jobType) {
      byJobType = summary;
    }
  }

  return byJobId ?? byJobType ?? firstSummary;
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
  const roadSummary = asRecord(bundle.roadSummary) ?? {};
  const roadwaySubmission = asRecord(bundle.roadwaySubmission) ?? {};
  const engines = asRecord(results.engines);
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
  const engineSummary = extractEngineSummary(results, asString(job?.id), asString(job?.type));
  const engineSummaries: JsonRecord[] = [];
  if (engines) {
    for (const [engineId, payload] of Object.entries(engines)) {
      const engine = asRecord(payload);
      if (!engine) {
        continue;
      }
      const summaryRec = asRecord(engine.summary);
      engineSummaries.push({
        engine_id: engineId,
        job_id: asString(engine.job_id) ?? "",
        job_type: asString(engine.job_type) ?? "",
        backend: asString(engine.backend) ?? "",
        summary_keys: summaryRec ? Object.keys(summaryRec).join(", ") : "",
      });
    }
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

  const residualsRaw = summary.residuals ?? engineSummary?.residuals;
  const residuals = Array.isArray(residualsRaw)
    ? residualsRaw.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
    : [];
  const energyBalanceHistoryRaw = summary.energy_balance_history ?? engineSummary?.energy_balance_history;
  const energyBalanceHistory = Array.isArray(energyBalanceHistoryRaw)
    ? energyBalanceHistoryRaw.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
    : [];
  const solverStatus = asRecord(summary.solver_status) ?? asRecord(engineSummary?.solver_status);
  const energy = asRecord(summary.energy) ?? asRecord(engineSummary?.energy);
  const radiosityDiagnostics = asRecord(summary.radiosity_diagnostics) ?? asRecord(engineSummary?.radiosity_diagnostics);
  const radiosityAvailable =
    job?.type === "radiosity" || residuals.length > 0 || solverStatus !== null || energy !== null;

  const ugrViews = asRecordList(summary.ugr_views ?? engineSummary?.ugr_views);
  const ugrDebug = asRecord(summary.ugr_debug) ?? asRecord(engineSummary?.ugr_debug);
  const ugrWorstCase = asNumber(summary.ugr_worst_case) ?? asNumber(summary.highest_ugr) ?? asNumber(engineSummary?.ugr_worst_case);
  const debugTopContributors = asRecordList(ugrDebug?.top_contributors);
  const viewTopContributors: JsonRecord[] = [];
  for (const view of ugrViews) {
    const viewName = asString(view.name) ?? "View";
    for (const row of asRecordList(view.top_contributors)) {
      viewTopContributors.push({
        view_name: viewName,
        luminaire_id: asString(row.luminaire_id),
        contribution: asNumber(row.contribution),
        luminance_est: asNumber(row.luminance_est),
        omega: asNumber(row.omega),
        position_index: asNumber(row.position_index),
      });
    }
  }
  const ugrAvailable =
    typeof ugrWorstCase === "number" ||
    ugrViews.length > 0 ||
    ugrDebug !== null ||
    debugTopContributors.length > 0 ||
    viewTopContributors.length > 0;

  const roadwayProfile = asRecord(summary.roadway_profile) ?? asRecord(engineSummary?.roadway_profile);
  const roadway = asRecord(summary.roadway) ?? asRecord(engineSummary?.roadway);
  const roadwayCompliance = asRecord(summary.compliance) ?? asRecord(engineSummary?.compliance);
  const observerGlareViews = asRecordList(summary.observer_glare_views ?? engineSummary?.observer_glare_views);
  const laneMetrics = asRecordList(summary.lane_metrics ?? engineSummary?.lane_metrics ?? summary.lanes ?? engineSummary?.lanes);
  const observerLuminanceViews = asRecordList(
    summary.observer_luminance_views ?? engineSummary?.observer_luminance_views,
  );
  const tiObservers = asRecordList(summary.ti_observers ?? engineSummary?.ti_observers);
  const luminanceModel = asRecord(summary.luminance_model) ?? asRecord(engineSummary?.luminance_model);
  const roadwayAvailable =
    job?.type === "roadway" ||
    roadwayProfile !== null ||
    roadway !== null ||
    roadwayCompliance !== null ||
    laneMetrics.length > 0 ||
    observerLuminanceViews.length > 0 ||
    tiObservers.length > 0 ||
    observerGlareViews.length > 0;

  const typedSubmission = Object.keys(roadwaySubmission).length > 0 ? roadwaySubmission : roadSummary;
  const typedSubmissionSource =
    Object.keys(roadwaySubmission).length > 0
      ? "roadway_submission.json"
      : Object.keys(roadSummary).length > 0
        ? "road_summary.json"
        : "none";
  const submissionChecks = asRecordList(typedSubmission.checks);
  const submissionOverall = asRecord(typedSubmission.overall);
  const submissionProfile = asRecord(typedSubmission.profile);
  const submissionValidationIssues: string[] = [];
  if (typedSubmissionSource !== "none") {
    if (!asString(typedSubmission.status)) {
      submissionValidationIssues.push("Missing roadway submission status.");
    }
    if (submissionChecks.length === 0) {
      submissionValidationIssues.push("No roadway submission checks present.");
    }
    for (const [idx, check] of submissionChecks.entries()) {
      if (!asString(check.metric)) {
        submissionValidationIssues.push(`Check #${idx + 1}: missing metric.`);
      }
      if (!asString(check.comparator)) {
        submissionValidationIssues.push(`Check #${idx + 1}: missing comparator.`);
      }
      if (asNumber(check.actual) === undefined) {
        submissionValidationIssues.push(`Check #${idx + 1}: missing/invalid actual.`);
      }
      if (asNumber(check.target) === undefined) {
        submissionValidationIssues.push(`Check #${idx + 1}: missing/invalid target.`);
      }
    }
  }

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
    roadwaySubmission: {
      available: typedSubmissionSource !== "none",
      source: typedSubmissionSource,
      title: asString(typedSubmission.title),
      status: asString(typedSubmission.status),
      profile: submissionProfile,
      overall: submissionOverall,
      checks: submissionChecks,
      validationIssues: submissionValidationIssues,
    },
    raw: { result, tables, results, roadSummary, roadwaySubmission },
    engines: {
      available: engineSummaries.length > 0,
      summaries: engineSummaries,
    },
    radiosity: {
      available: radiosityAvailable,
      converged: asBoolean(summary.converged),
      iterations: asNumber(summary.iterations),
      stopReason: asString(summary.stop_reason),
      residuals,
      energyBalanceHistory,
      solverStatus,
      energy,
      diagnostics: radiosityDiagnostics,
      residualThreshold: asNumber(summary.residual_threshold) ?? asNumber(engineSummary?.residual_threshold),
      residualBelowThreshold:
        asBoolean(summary.residual_below_threshold) ?? asBoolean(engineSummary?.residual_below_threshold),
      residualNonincreasing: asBoolean(summary.residual_nonincreasing) ?? asBoolean(engineSummary?.residual_nonincreasing),
    },
    ugr: {
      available: ugrAvailable,
      worstCase: ugrWorstCase,
      views: ugrViews,
      debug: ugrDebug,
      debugTopContributors,
      viewTopContributors,
    },
    roadway: {
      available: roadwayAvailable,
      roadClass: asString(summary.road_class) ?? asString(engineSummary?.road_class),
      roadwayProfile,
      roadway,
      compliance: roadwayCompliance,
      laneMetrics,
      observerLuminanceViews,
      tiObservers,
      observerGlareViews,
      luminanceModel,
    },
  };
}
