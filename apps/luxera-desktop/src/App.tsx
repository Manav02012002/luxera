import { useEffect, useMemo, useRef, useState } from "react";
import {
  AppShell,
  ConsolePanel,
  InspectorPanel,
  MetricCard,
  Sidebar,
  SidebarSection,
  ToolbarButton,
} from "@luxera/luxera-ui";
import { buildDesktopViewModel, type DesktopResultBundle, type DesktopViewModel } from "./resultContracts";

const projectItems = ["Project", "Geometry", "Luminaires", "Calculation", "Reports"];
type JsonRow = Record<string, unknown>;
type SortDir = "asc" | "desc";

interface RecentRun {
  resultDir: string;
  modifiedUnixS: number;
  jobId?: string | null;
  jobType?: string | null;
  contractVersion?: string | null;
}

interface ArtifactRead {
  path: string;
  sizeBytes: number;
  truncated: boolean;
  content: string;
}

interface BackendContract {
  contract_version: string;
  required_files: string[];
  optional_files: string[];
  rendered_sections: string[];
  max_read_artifact_bytes_default: number;
}

interface ProjectJob {
  id: string;
  jobType: string;
  backend: string;
  seed: number;
}

interface ProjectJobsResponse {
  projectPath: string;
  projectName?: string | null;
  jobs: ProjectJob[];
}

interface JobRunResponse {
  projectPath: string;
  jobId: string;
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  resultDir?: string | null;
}

interface JobRunStartResponse {
  runId: number;
  projectPath: string;
  jobId: string;
}

interface JobRunPollResponse {
  runId: number;
  done: boolean;
  success: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  resultDir?: string | null;
}

type RunStatus = "idle" | "starting" | "running" | "completed" | "failed" | "cancelled";

interface RunTimelineEvent {
  atUnixMs: number;
  status: RunStatus;
  message: string;
}

interface RunHistoryEntry {
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

interface AppState {
  resultDir: string;
  loading: boolean;
  error: string;
  bundle: DesktopResultBundle | null;
  model: DesktopViewModel | null;
  recentRuns: RecentRun[];
  recentLoading: boolean;
  contract: BackendContract | null;
  artifactPath: string;
  artifact: ArtifactRead | null;
  artifactLoading: boolean;
  artifactError: string;
  projectPath: string;
  projectName: string;
  projectJobs: ProjectJob[];
  jobsLoading: boolean;
  selectedJobId: string;
  runLoading: boolean;
  runResult: JobRunResponse | null;
  runError: string;
  activeRunId: number | null;
  activeRunProjectPath: string;
  activeRunProjectName: string;
  activeRunJobId: string;
  runStdout: string;
  runStderr: string;
  runStatus: RunStatus;
  runTimeline: RunTimelineEvent[];
  runHistory: RunHistoryEntry[];
  runHistorySeq: number;
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

async function tauriInvoke<T>(cmd: string, args: Record<string, unknown>): Promise<T> {
  const tauri = (window as Window & { __TAURI__?: { core?: { invoke?: (c: string, a: unknown) => Promise<unknown> } } })
    .__TAURI__;
  const invokeFn = tauri?.core?.invoke;
  if (!invokeFn) {
    throw new Error("Tauri runtime API unavailable.");
  }
  return (await invokeFn(cmd, args)) as T;
}

function scalarText(value: unknown): string {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(Math.abs(value) >= 100 ? 1 : 3) : "NaN";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "-";
  }
  return JSON.stringify(value);
}

function DataTable({ title, rows }: { title: string; rows: JsonRow[] }) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const columns = useMemo(() => {
    const keys = new Set<string>();
    for (const row of rows) {
      for (const key of Object.keys(row)) {
        keys.add(key);
      }
    }
    return Array.from(keys);
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!query.trim()) {
      return rows;
    }
    const q = query.trim().toLowerCase();
    return rows.filter((row) => Object.values(row).some((v) => scalarText(v).toLowerCase().includes(q)));
  }, [rows, query]);

  const orderedRows = useMemo(() => {
    if (!sortKey) {
      return filteredRows;
    }
    const out = [...filteredRows];
    out.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const an = typeof av === "number" ? av : Number.NaN;
      const bn = typeof bv === "number" ? bv : Number.NaN;
      if (Number.isFinite(an) && Number.isFinite(bn)) {
        return sortDir === "asc" ? an - bn : bn - an;
      }
      const as = scalarText(av).toLowerCase();
      const bs = scalarText(bv).toLowerCase();
      if (as < bs) {
        return sortDir === "asc" ? -1 : 1;
      }
      if (as > bs) {
        return sortDir === "asc" ? 1 : -1;
      }
      return 0;
    });
    return out;
  }, [filteredRows, sortDir, sortKey]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir("asc");
  };

  return (
    <section className="rounded-md border border-border bg-panel p-3">
      <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">
        {title} ({orderedRows.length}/{rows.length})
      </div>
      <div className="mb-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter rows..."
          className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
        />
      </div>
      {rows.length === 0 ? (
        <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">No rows.</div>
      ) : (
        <div className="max-h-56 overflow-auto rounded border border-border/60">
          <table className="min-w-full text-xs">
            <thead className="sticky top-0 bg-panel">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">
                    <button type="button" className="text-left" onClick={() => toggleSort(col)}>
                      {col}
                      {sortKey === col ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orderedRows.map((row, idx) => (
                <tr key={`${title}-${idx}`} className="odd:bg-panelSoft/30">
                  {columns.map((col) => (
                    <td key={`${title}-${idx}-${col}`} className="border-b border-border/50 px-2 py-1 align-top text-text">
                      {scalarText(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function objectToRows(obj: JsonRow | null | undefined): JsonRow[] {
  if (!obj) {
    return [];
  }
  return Object.entries(obj).map(([key, value]) => ({ key, value: scalarText(value) }));
}

export default function App() {
  const [state, setState] = useState<AppState>({
    resultDir: "",
    loading: false,
    error: "",
    bundle: null,
    model: null,
    recentRuns: [],
    recentLoading: false,
    contract: null,
    artifactPath: "",
    artifact: null,
    artifactLoading: false,
    artifactError: "",
    projectPath: "",
    projectName: "",
    projectJobs: [],
    jobsLoading: false,
    selectedJobId: "",
    runLoading: false,
    runResult: null,
    runError: "",
    activeRunId: null,
    activeRunProjectPath: "",
    activeRunProjectName: "",
    activeRunJobId: "",
    runStdout: "",
    runStderr: "",
    runStatus: "idle",
    runTimeline: [],
    runHistory: [],
    runHistorySeq: 0,
  });
  const hasTauri = "__TAURI_INTERNALS__" in window;
  const pollTimerRef = useRef<number | null>(null);
  const startRunLockRef = useRef(false);

  const model = state.model;

  const refreshRecentRuns = async (): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    setState((s) => ({ ...s, recentLoading: true }));
    try {
      const runs = await tauriInvoke<RecentRun[]>("list_recent_runs", { limit: 20 });
      setState((s) => ({ ...s, recentRuns: runs, recentLoading: false }));
    } catch {
      setState((s) => ({ ...s, recentLoading: false }));
    }
  };

  const loadContract = async (): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    try {
      const contract = await tauriInvoke<BackendContract>("desktop_backend_contract", {});
      setState((s) => ({ ...s, contract }));
    } catch {
      // Best effort only.
    }
  };

  const loadOutputs = async (explicitDir?: string): Promise<void> => {
    if (!hasTauri) {
      setState((s) => ({
        ...s,
        error: "Backend loading requires Tauri runtime (use `pnpm --filter luxera-desktop tauri:dev`).",
      }));
      return;
    }
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const payload = await tauriInvoke<DesktopResultBundle>("load_backend_outputs", {
        resultDir: explicitDir?.trim() ? explicitDir.trim() : null,
      });
      const nextModel = buildDesktopViewModel(payload);
      setState((s) => ({
        ...s,
        bundle: payload,
        model: nextModel,
        resultDir: payload.sourceDir,
        loading: false,
        artifactPath: `${payload.sourceDir}/result.json`,
      }));
      await refreshRecentRuns();
    } catch (err) {
      setState((s) => ({
        ...s,
        bundle: null,
        model: null,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  };

  const openResultDir = async (path: string): Promise<void> => {
    if (!hasTauri || !path.trim()) {
      return;
    }
    try {
      await tauriInvoke<void>("open_result_dir", { path });
    } catch (err) {
      setState((s) => ({ ...s, error: err instanceof Error ? err.message : String(err) }));
    }
  };

  const loadProjectJobs = async (): Promise<void> => {
    if (!hasTauri) {
      setState((s) => ({ ...s, runError: "Project/job loading requires Tauri runtime." }));
      return;
    }
    const path = state.projectPath.trim();
    if (!path) {
      setState((s) => ({ ...s, runError: "Project path is empty." }));
      return;
    }
    setState((s) => ({ ...s, jobsLoading: true, runError: "", runResult: null }));
    try {
      const payload = await tauriInvoke<ProjectJobsResponse>("list_project_jobs", { projectPath: path });
      const selectedJobId = payload.jobs.length > 0 ? payload.jobs[0].id : "";
      setState((s) => ({
        ...s,
        jobsLoading: false,
        projectPath: payload.projectPath,
        projectName: payload.projectName ?? "",
        projectJobs: payload.jobs,
        selectedJobId,
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        jobsLoading: false,
        runError: err instanceof Error ? err.message : String(err),
      }));
    }
  };

  const runSelectedJob = async (): Promise<void> => {
    if (!hasTauri) {
      setState((s) => ({ ...s, runError: "Running jobs requires Tauri runtime." }));
      return;
    }
    if (startRunLockRef.current || state.runLoading || state.activeRunId !== null) {
      setState((s) => ({ ...s, runError: "A run is already in progress." }));
      return;
    }
    const projectPath = state.projectPath.trim();
    const jobId = state.selectedJobId.trim();
    if (!projectPath || !jobId) {
      setState((s) => ({ ...s, runError: "Project path and selected job are required." }));
      return;
    }
    startRunLockRef.current = true;
    const startedAtUnixMs = Date.now();
    const localId = state.runHistorySeq + 1;
    setState((s) => ({
      ...s,
      runLoading: true,
      runError: "",
      runResult: null,
      runStdout: "",
      runStderr: "",
      activeRunId: null,
      activeRunProjectPath: projectPath,
      activeRunProjectName: s.projectName,
      activeRunJobId: jobId,
      runStatus: "starting",
      runTimeline: [...s.runTimeline, { atUnixMs: startedAtUnixMs, status: "starting", message: `Starting ${jobId}` }],
      runHistorySeq: localId,
      runHistory: [
        {
          localId,
          runId: null,
          projectPath,
          projectName: s.projectName,
          jobId,
          startedAtUnixMs,
          endedAtUnixMs: null,
          status: "starting",
          success: null,
          exitCode: null,
          stdout: "",
          stderr: "",
          resultDir: null,
        },
        ...s.runHistory.slice(0, 24),
      ],
    }));
    try {
      const start = await tauriInvoke<JobRunStartResponse>("start_project_job_run", { projectPath, jobId });
      setState((s) => ({
        ...s,
        activeRunId: start.runId,
        runStatus: "running",
        runTimeline: [...s.runTimeline, { atUnixMs: Date.now(), status: "running", message: `Run #${start.runId} started` }],
        runHistory: s.runHistory.map((entry) =>
          entry.localId === localId ? { ...entry, runId: start.runId, status: "running" } : entry,
        ),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState((s) => ({
        ...s,
        runLoading: false,
        runError: message,
        runStatus: "failed",
        runTimeline: [...s.runTimeline, { atUnixMs: Date.now(), status: "failed", message: `Start failed: ${message}` }],
        runHistory: s.runHistory.map((entry) =>
          entry.localId === localId
            ? { ...entry, endedAtUnixMs: Date.now(), status: "failed", stderr: message, success: false }
            : entry,
        ),
      }));
    } finally {
      startRunLockRef.current = false;
    }
  };

  const cancelActiveRun = async (): Promise<void> => {
    if (!hasTauri || state.activeRunId === null) {
      return;
    }
    try {
      const payload = await tauriInvoke<JobRunPollResponse>("cancel_project_job_run", { runId: state.activeRunId });
      const runResult: JobRunResponse = {
        projectPath: state.activeRunProjectPath || state.projectPath,
        jobId: state.activeRunJobId || state.selectedJobId,
        success: payload.success,
        exitCode: payload.exitCode,
        stdout: payload.stdout,
        stderr: payload.stderr,
        resultDir: payload.resultDir ?? null,
      };
      setState((s) => ({
        ...s,
        runLoading: false,
        activeRunId: null,
        runResult,
        runStdout: payload.stdout,
        runStderr: payload.stderr,
        runStatus: "cancelled",
        runTimeline: [...s.runTimeline, { atUnixMs: Date.now(), status: "cancelled", message: `Run #${payload.runId} cancelled` }],
        runHistory: s.runHistory.map((entry) =>
          entry.runId === payload.runId
            ? {
                ...entry,
                endedAtUnixMs: Date.now(),
                status: "cancelled",
                success: payload.success,
                exitCode: payload.exitCode,
                stdout: payload.stdout,
                stderr: payload.stderr,
                resultDir: payload.resultDir ?? null,
              }
            : entry,
        ),
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        runLoading: false,
        activeRunId: null,
        runError: err instanceof Error ? err.message : String(err),
        runStatus: "failed",
        runTimeline: [...s.runTimeline, { atUnixMs: Date.now(), status: "failed", message: "Cancel failed" }],
      }));
    }
  };

  useEffect(() => {
    if (!hasTauri || state.activeRunId === null) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    const pollOnce = async (): Promise<void> => {
      try {
        const payload = await tauriInvoke<JobRunPollResponse>("poll_project_job_run", { runId: state.activeRunId });
        setState((s) => ({
          ...s,
          runStdout: payload.stdout,
          runStderr: payload.stderr,
          runHistory: s.runHistory.map((entry) =>
            entry.runId === payload.runId ? { ...entry, stdout: payload.stdout, stderr: payload.stderr } : entry,
          ),
        }));

        if (payload.done) {
          const projectPath = state.activeRunProjectPath || state.projectPath;
          const jobId = state.activeRunJobId || state.selectedJobId;
          const doneStatus: RunStatus = payload.success ? "completed" : "failed";
          const runResult: JobRunResponse = {
            projectPath,
            jobId,
            success: payload.success,
            exitCode: payload.exitCode,
            stdout: payload.stdout,
            stderr: payload.stderr,
            resultDir: payload.resultDir ?? null,
          };
          setState((s) => ({
            ...s,
            runLoading: false,
            activeRunId: null,
            runResult,
            runStdout: payload.stdout,
            runStderr: payload.stderr,
            runStatus: doneStatus,
            runTimeline: [
              ...s.runTimeline,
              {
                atUnixMs: Date.now(),
                status: doneStatus,
                message: `Run #${payload.runId} ${doneStatus} (exit ${payload.exitCode})`,
              },
            ],
            runHistory: s.runHistory.map((entry) =>
              entry.runId === payload.runId
                ? {
                    ...entry,
                    endedAtUnixMs: Date.now(),
                    status: doneStatus,
                    success: payload.success,
                    exitCode: payload.exitCode,
                    stdout: payload.stdout,
                    stderr: payload.stderr,
                    resultDir: payload.resultDir ?? null,
                  }
                : entry,
            ),
          }));
          if (payload.resultDir) {
            await loadOutputs(payload.resultDir);
          } else {
            await refreshRecentRuns();
          }
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setState((s) => ({
          ...s,
          runLoading: false,
          activeRunId: null,
          runError: message,
          runStatus: "failed",
          runTimeline: [...s.runTimeline, { atUnixMs: Date.now(), status: "failed", message: `Polling failed: ${message}` }],
        }));
      }
    };

    void pollOnce();
    pollTimerRef.current = window.setInterval(() => {
      void pollOnce();
    }, 750);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.activeRunId, state.activeRunJobId, state.activeRunProjectPath, state.projectPath, state.selectedJobId, hasTauri]);

  const readArtifact = async (): Promise<void> => {
    if (!hasTauri) {
      setState((s) => ({ ...s, artifactError: "Artifact reading requires Tauri runtime." }));
      return;
    }
    const path = state.artifactPath.trim();
    if (!path) {
      setState((s) => ({ ...s, artifactError: "Artifact path is empty." }));
      return;
    }
    setState((s) => ({ ...s, artifactLoading: true, artifactError: "", artifact: null }));
    try {
      const artifact = await tauriInvoke<ArtifactRead>("read_artifact", { path, maxBytes: null });
      setState((s) => ({ ...s, artifact, artifactLoading: false }));
    } catch (err) {
      setState((s) => ({
        ...s,
        artifactLoading: false,
        artifactError: err instanceof Error ? err.message : String(err),
      }));
    }
  };

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
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-[2fr_1fr]">
              <label className="block">
                <span className="mb-1 block text-xs uppercase tracking-[0.12em] text-muted">Result Directory</span>
                <input
                  value={state.resultDir}
                  onChange={(e) => setState((s) => ({ ...s, resultDir: e.target.value }))}
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
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Run Control</div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr]">
                <input
                  value={state.projectPath}
                  onChange={(e) => setState((s) => ({ ...s, projectPath: e.target.value }))}
                  placeholder="Project file path (.json)"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void loadProjectJobs()} disabled={state.jobsLoading || state.runLoading}>
                  {state.jobsLoading ? "Loading Jobs..." : "Load Jobs"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void runSelectedJob()} disabled={state.runLoading || state.jobsLoading}>
                  {state.runLoading ? "Running..." : "Run Selected Job"}
                </ToolbarButton>
                <ToolbarButton onClick={() => void cancelActiveRun()} disabled={!state.runLoading || state.activeRunId === null}>
                  Cancel
                </ToolbarButton>
              </div>
              <div className="mb-2 grid grid-cols-1 gap-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
                <select
                  value={state.selectedJobId}
                  onChange={(e) => setState((s) => ({ ...s, selectedJobId: e.target.value }))}
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
                  Last exit: {state.runResult ? String(state.runResult.exitCode) : "N/A"}
                </div>
                <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">
                  Status: {state.runStatus}
                </div>
              </div>
              {state.runError ? <div className="mb-2 text-xs text-rose-300">{state.runError}</div> : null}
              {state.runLoading || state.runResult ? (
                <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">stdout</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap">
                      {(state.runLoading ? state.runStdout : state.runResult?.stdout) || "(empty)"}
                    </pre>
                  </div>
                  <div className="rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                    <div className="mb-1 text-text">stderr</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap">
                      {(state.runLoading ? state.runStderr : state.runResult?.stderr) || "(empty)"}
                    </pre>
                  </div>
                </div>
              ) : null}
              {state.runTimeline.length > 0 ? (
                <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                  <div className="mb-1 text-text">Run Timeline</div>
                  <div className="max-h-32 space-y-1 overflow-auto">
                    {state.runTimeline
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
              {state.runHistory.length > 0 ? (
                <div className="mt-2 rounded border border-border/60 bg-panelSoft/50 p-2 text-xs text-muted">
                  <div className="mb-1 text-text">Run History</div>
                  <div className="max-h-48 space-y-1 overflow-auto">
                    {state.runHistory.map((entry) => (
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
                {model.radiosity.residuals.length > 0 ? (
                  <DataTable
                    title="Radiosity Residual Trace"
                    rows={model.radiosity.residuals.map((value, index) => ({ iteration: index + 1, residual: value }))}
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
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="UGR Views" rows={model.ugr.views} />
                  <DataTable title="UGR Debug" rows={objectToRows(model.ugr.debug)} />
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
                </div>
                <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
                  <DataTable title="Roadway Profile" rows={objectToRows(model.roadway.roadwayProfile)} />
                  <DataTable title="Roadway Summary Block" rows={objectToRows(model.roadway.roadway)} />
                </div>
                <DataTable title="Roadway Observer Glare Views" rows={model.roadway.observerGlareViews} />
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
            <DataTable title="Grids" rows={(model?.tables.grids ?? []) as JsonRow[]} />
            <DataTable title="Vertical Planes" rows={(model?.tables.verticalPlanes ?? []) as JsonRow[]} />
            <DataTable title="Point Sets" rows={(model?.tables.pointSets ?? []) as JsonRow[]} />
            <DataTable title="Indoor Planes" rows={(model?.indoorPlanes ?? []) as JsonRow[]} />
            <DataTable title="Zone Metrics" rows={(model?.zoneMetrics ?? []) as JsonRow[]} />
            <section className="rounded-md border border-border bg-panel p-3">
              <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">Artifact Reader</div>
              <div className="mb-2 flex gap-2">
                <input
                  value={state.artifactPath}
                  onChange={(e) => setState((s) => ({ ...s, artifactPath: e.target.value }))}
                  placeholder="Path to artifact file"
                  className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
                />
                <ToolbarButton onClick={() => void readArtifact()} disabled={state.artifactLoading}>
                  {state.artifactLoading ? "Reading..." : "Read"}
                </ToolbarButton>
              </div>
              {state.artifactError ? <div className="mb-2 text-xs text-rose-300">{state.artifactError}</div> : null}
              {state.artifact ? (
                <div className="text-xs text-muted">
                  <div className="mb-1">{state.artifact.path} ({state.artifact.sizeBytes} bytes){state.artifact.truncated ? " [truncated]" : ""}</div>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-border/60 bg-panelSoft/50 p-2 text-[11px] text-text">
                    {state.artifact.content}
                  </pre>
                </div>
              ) : null}
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
