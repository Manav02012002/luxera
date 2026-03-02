import { useEffect, useRef, useState } from "react";
import type {
  JobRunPollResponse,
  JobRunResponse,
  JobRunStartResponse,
  RunHistoryEntry,
  RunStatus,
  RunTimelineEvent,
} from "../types";
import { tauriInvoke } from "../utils/tauri";

interface UseJobRunnerArgs {
  hasTauri: boolean;
  projectPath: string;
  selectedJobId: string;
  projectName: string;
  onResultDir: (resultDir: string) => Promise<void>;
  onNoResultDir: () => Promise<void>;
}

interface JobRunnerState {
  runLoading: boolean;
  runResult: JobRunResponse | null;
  runError: string;
  activeRunId: number | null;
  activeRunProjectPath: string;
  activeRunJobId: string;
  runStdout: string;
  runStderr: string;
  runStatus: RunStatus;
  runTimeline: RunTimelineEvent[];
  runHistory: RunHistoryEntry[];
  runHistorySeq: number;
}

function nextPollDelayMs(elapsedMs: number): number {
  if (elapsedMs < 5000) {
    return 250;
  }
  if (elapsedMs < 20000) {
    return 750;
  }
  return 2000;
}

export function useJobRunner({
  hasTauri,
  projectPath,
  selectedJobId,
  projectName,
  onResultDir,
  onNoResultDir,
}: UseJobRunnerArgs) {
  const [state, setState] = useState<JobRunnerState>({
    runLoading: false,
    runResult: null,
    runError: "",
    activeRunId: null,
    activeRunProjectPath: "",
    activeRunJobId: "",
    runStdout: "",
    runStderr: "",
    runStatus: "idle",
    runTimeline: [],
    runHistory: [],
    runHistorySeq: 0,
  });
  const startRunLockRef = useRef(false);
  const pollTimerRef = useRef<number | null>(null);
  const runStartedAtRef = useRef<number>(0);

  const runSelectedJob = async (): Promise<void> => {
    if (!hasTauri) {
      setState((s) => ({ ...s, runError: "Running jobs requires Tauri runtime." }));
      return;
    }
    if (startRunLockRef.current || state.runLoading || state.activeRunId !== null) {
      setState((s) => ({ ...s, runError: "A run is already in progress." }));
      return;
    }
    const runProjectPath = projectPath.trim();
    const jobId = selectedJobId.trim();
    if (!runProjectPath || !jobId) {
      setState((s) => ({ ...s, runError: "Project path and selected job are required." }));
      return;
    }

    startRunLockRef.current = true;
    const startedAtUnixMs = Date.now();
    runStartedAtRef.current = startedAtUnixMs;
    const localId = state.runHistorySeq + 1;
    setState((s) => ({
      ...s,
      runLoading: true,
      runError: "",
      runResult: null,
      runStdout: "",
      runStderr: "",
      activeRunId: null,
      activeRunProjectPath: runProjectPath,
      activeRunJobId: jobId,
      runStatus: "starting",
      runTimeline: [...s.runTimeline, { atUnixMs: startedAtUnixMs, status: "starting", message: `Starting ${jobId}` }],
      runHistorySeq: localId,
      runHistory: [
        {
          localId,
          runId: null,
          projectPath: runProjectPath,
          projectName,
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
      const start = await tauriInvoke<JobRunStartResponse>("start_project_job_run", { projectPath: runProjectPath, jobId });
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
        projectPath: state.activeRunProjectPath || projectPath,
        jobId: state.activeRunJobId || selectedJobId,
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
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    let cancelled = false;
    const pollOnce = async (): Promise<void> => {
      try {
        const payload = await tauriInvoke<JobRunPollResponse>("poll_project_job_run", { runId: state.activeRunId });
        if (cancelled) {
          return;
        }
        setState((s) => ({
          ...s,
          runStdout: payload.stdout,
          runStderr: payload.stderr,
          runHistory: s.runHistory.map((entry) =>
            entry.runId === payload.runId ? { ...entry, stdout: payload.stdout, stderr: payload.stderr } : entry,
          ),
        }));
        if (payload.done) {
          const finalProjectPath = state.activeRunProjectPath || projectPath;
          const finalJobId = state.activeRunJobId || selectedJobId;
          const doneStatus: RunStatus = payload.success ? "completed" : "failed";
          const runResult: JobRunResponse = {
            projectPath: finalProjectPath,
            jobId: finalJobId,
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
            await onResultDir(payload.resultDir);
          } else {
            await onNoResultDir();
          }
          return;
        }

        const elapsed = Date.now() - runStartedAtRef.current;
        const delayMs = nextPollDelayMs(elapsed);
        pollTimerRef.current = window.setTimeout(() => {
          void pollOnce();
        }, delayMs);
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
    return () => {
      cancelled = true;
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [state.activeRunId, state.activeRunJobId, state.activeRunProjectPath, hasTauri, onNoResultDir, onResultDir, projectPath, selectedJobId]);

  return {
    ...state,
    runSelectedJob,
    cancelActiveRun,
  };
}
