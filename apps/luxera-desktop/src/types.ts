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

export interface AppState {
  resultDir: string;
  loading: boolean;
  error: string;
  bundle: DesktopResultBundle | null;
  model: DesktopViewModel | null;
  recentRuns: RecentRun[];
  recentLoading: boolean;
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
  selectedTableTitle: string;
  selectedRowIndex: number;
  selectedRow: JsonRow | null;
}
