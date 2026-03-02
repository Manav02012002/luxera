import { useEffect, useReducer } from "react";
import type { ProjectDocument, ProjectJobsResponse, ProjectValidationResult } from "../types";
import { tauriDialogOpen, tauriDialogSave, tauriInvoke } from "../utils/tauri";

const RECENT_PROJECTS_STORAGE_KEY = "luxera.desktop.recentProjects";
const MAX_RECENT_PROJECTS = 15;

export interface ProjectState {
  projectPath: string;
  projectName: string;
  projectJobs: ProjectJobsResponse["jobs"];
  selectedJobId: string;
  projectDoc: ProjectDocument | null;
  projectDocContent: string;
  projectDocDirty: boolean;
  projectValidation: ProjectValidationResult | null;
  projectLifecycleLoading: boolean;
  projectLifecycleError: string;
  recentProjects: string[];
  jobsLoading: boolean;
}

type ProjectAction =
  | { type: "patch"; patch: Partial<ProjectState> }
  | { type: "set_project_path"; projectPath: string }
  | { type: "set_recent_projects"; recentProjects: string[] };

function reducer(state: ProjectState, action: ProjectAction): ProjectState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    case "set_project_path":
      return { ...state, projectPath: action.projectPath };
    case "set_recent_projects":
      return { ...state, recentProjects: action.recentProjects };
    default:
      return state;
  }
}

interface UseProjectStateArgs {
  hasTauri: boolean;
}

export function useProjectState({ hasTauri }: UseProjectStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    projectPath: "",
    projectName: "",
    projectJobs: [],
    selectedJobId: "",
    projectDoc: null,
    projectDocContent: "",
    projectDocDirty: false,
    projectValidation: null,
    projectLifecycleLoading: false,
    projectLifecycleError: "",
    recentProjects: [],
    jobsLoading: false,
  });

  const patch = (patchState: Partial<ProjectState>): void => {
    dispatch({ type: "patch", patch: patchState });
  };

  const persistRecentProjects = async (paths: string[]): Promise<void> => {
    if (hasTauri) {
      try {
        await tauriInvoke<boolean>("save_recent_projects_store", { projects: paths });
        return;
      } catch {
        // fallback below
      }
    }
    try {
      window.localStorage.setItem(RECENT_PROJECTS_STORAGE_KEY, JSON.stringify(paths));
    } catch {
      // best effort
    }
  };

  const pushRecentProjectPath = (projectPath: string): void => {
    const normalized = projectPath.trim();
    if (!normalized) {
      return;
    }
    const next = [normalized, ...state.recentProjects.filter((p) => p !== normalized)].slice(0, MAX_RECENT_PROJECTS);
    patch({ recentProjects: next });
    void persistRecentProjects(next);
  };

  const browseProjectPath = async (defaultPath?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project browsing requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Open Luxera Project",
        defaultPath: (defaultPath ?? state.projectPath).trim() || undefined,
        multiple: false,
        directory: false,
        filters: [{ name: "Project JSON", extensions: ["json"] }],
      });
      if (typeof picked === "string" && picked.trim()) {
        patch({ projectPath: picked, projectLifecycleError: "" });
      }
    } catch (err) {
      patch({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const openProjectDocument = async (pathOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (pathOverride ?? state.projectPath).trim();
    if (!projectPath) {
      patch({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patch({ projectLifecycleLoading: true, projectLifecycleError: "", projectValidation: null });
    try {
      const doc = await tauriInvoke<ProjectDocument>("open_project_file", { projectPath });
      patch({
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
      patch({ projectLifecycleLoading: false, projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const openProjectFromDialog = async (defaultPath?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogOpen({
        title: "Open Luxera Project",
        defaultPath: (defaultPath ?? state.projectPath).trim() || undefined,
        multiple: false,
        directory: false,
        filters: [{ name: "Project JSON", extensions: ["json"] }],
      });
      if (typeof picked === "string" && picked.trim()) {
        await openProjectDocument(picked);
      }
    } catch (err) {
      patch({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const initProjectDocument = async (pathOverride?: string, nameOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (pathOverride ?? state.projectPath).trim();
    if (!projectPath) {
      patch({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patch({ projectLifecycleLoading: true, projectLifecycleError: "", projectValidation: null });
    try {
      const doc = await tauriInvoke<ProjectDocument>("init_project_file", {
        projectPath,
        name: (nameOverride ?? state.projectName).trim() || null,
      });
      patch({
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
      patch({ projectLifecycleLoading: false, projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const chooseNewProjectPathAndInit = async (defaultPath?: string, nameOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogSave({
        title: "Create New Luxera Project",
        defaultPath: (defaultPath ?? state.projectPath).trim() || undefined,
      });
      if (typeof picked === "string" && picked.trim()) {
        await initProjectDocument(picked, nameOverride);
      }
    } catch (err) {
      patch({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const saveProjectDocument = async (pathOverride?: string, contentOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (pathOverride ?? state.projectPath).trim();
    if (!projectPath) {
      patch({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patch({ projectLifecycleLoading: true, projectLifecycleError: "" });
    try {
      const doc = await tauriInvoke<ProjectDocument>("save_project_file", {
        projectPath,
        content: contentOverride ?? state.projectDocContent,
      });
      patch({
        projectLifecycleLoading: false,
        projectDoc: doc,
        projectDocContent: doc.content,
        projectDocDirty: false,
        projectPath: doc.path,
        projectName: doc.name,
      });
      pushRecentProjectPath(doc.path);
    } catch (err) {
      patch({ projectLifecycleLoading: false, projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const saveProjectAsDialog = async (defaultPath?: string, contentOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    try {
      const picked = await tauriDialogSave({
        title: "Save Luxera Project As",
        defaultPath: (defaultPath ?? state.projectPath).trim() || undefined,
      });
      if (typeof picked === "string" && picked.trim()) {
        await saveProjectDocument(picked, contentOverride);
      }
    } catch (err) {
      patch({ projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const validateProject = async (projectPathOverride?: string, jobIdOverride?: string): Promise<void> => {
    if (!hasTauri) {
      patch({ projectLifecycleError: "Project lifecycle requires Tauri runtime." });
      return;
    }
    const projectPath = (projectPathOverride ?? state.projectPath).trim();
    if (!projectPath) {
      patch({ projectLifecycleError: "Project path is empty." });
      return;
    }
    patch({ projectLifecycleLoading: true, projectLifecycleError: "" });
    try {
      const payload = await tauriInvoke<ProjectValidationResult>("validate_project_file", {
        projectPath,
        jobId: (jobIdOverride ?? state.selectedJobId).trim() || null,
      });
      patch({ projectLifecycleLoading: false, projectValidation: payload });
    } catch (err) {
      patch({ projectLifecycleLoading: false, projectLifecycleError: err instanceof Error ? err.message : String(err) });
    }
  };

  const loadProjectJobs = async (pathOverride?: string): Promise<void> => {
    if (!hasTauri) {
      return;
    }
    const path = (pathOverride ?? state.projectPath).trim();
    if (!path) {
      return;
    }
    patch({ jobsLoading: true });
    try {
      const payload = await tauriInvoke<ProjectJobsResponse>("list_project_jobs", { projectPath: path });
      const selectedJobId = payload.jobs.length > 0 ? payload.jobs[0].id : "";
      patch({
        jobsLoading: false,
        projectPath: payload.projectPath,
        projectName: payload.projectName ?? "",
        projectJobs: payload.jobs,
        selectedJobId,
      });
    } catch (err) {
      patch({
        jobsLoading: false,
        projectLifecycleError: err instanceof Error ? err.message : String(err),
      });
    }
  };

  useEffect(() => {
    const loadRecentProjects = async (): Promise<void> => {
      if (hasTauri) {
        try {
          const stored = await tauriInvoke<string[]>("load_recent_projects_store", {});
          const sanitized = (stored ?? [])
            .map((v) => String(v ?? "").trim())
            .filter((v) => v)
            .slice(0, MAX_RECENT_PROJECTS);
          if (sanitized.length > 0) {
            dispatch({ type: "set_recent_projects", recentProjects: sanitized });
          }
          return;
        } catch {
          // fallback below
        }
      }
      try {
        const raw = window.localStorage.getItem(RECENT_PROJECTS_STORAGE_KEY);
        if (!raw) {
          return;
        }
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) {
          return;
        }
        const sanitized = parsed
          .map((v) => String(v ?? "").trim())
          .filter((v) => v)
          .slice(0, MAX_RECENT_PROJECTS);
        if (sanitized.length > 0) {
          dispatch({ type: "set_recent_projects", recentProjects: sanitized });
        }
      } catch {
        // ignore
      }
    };
    void loadRecentProjects();
  }, [hasTauri]);

  return {
    state,
    patch,
    setProjectPath: (projectPath: string) => dispatch({ type: "set_project_path", projectPath }),
    setProjectName: (projectName: string) => patch({ projectName }),
    setSelectedJobId: (selectedJobId: string) => patch({ selectedJobId }),
    setProjectDocContent: (projectDocContent: string) => patch({ projectDocContent, projectDocDirty: true }),
    setRecentProjects: (recentProjects: string[]) => dispatch({ type: "set_recent_projects", recentProjects }),
    pushRecentProjectPath,
    browseProjectPath,
    openProjectFromDialog,
    openProjectDocument,
    chooseNewProjectPathAndInit,
    initProjectDocument,
    saveProjectDocument,
    saveProjectAsDialog,
    validateProject,
    loadProjectJobs,
  };
}
