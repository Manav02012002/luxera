import { useReducer } from "react";
import type { JsonRow, ToolOperationResult, VariantVisualResponse } from "../types";
import { tauriInvoke } from "../utils/tauri";

export interface DesignState {
  materialIdInput: string;
  materialSurfaceIdsCsv: string;
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
  variantVisualResult: VariantVisualResponse | null;
}

type Action = { type: "patch"; patch: Partial<DesignState> };

function reducer(state: DesignState, action: Action): DesignState {
  switch (action.type) {
    case "patch":
      return { ...state, ...action.patch };
    default:
      return state;
  }
}

interface UseDesignStateArgs {
  hasTauri: boolean;
  projectPath: string;
  selectedJobId: string;
  onProjectMutated: () => Promise<void>;
}

export function useDesignState({ hasTauri, projectPath, selectedJobId, onProjectMutated }: UseDesignStateArgs) {
  const [state, dispatch] = useReducer(reducer, {
    materialIdInput: "",
    materialSurfaceIdsCsv: "",
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
    variantVisualResult: null,
  });

  const patch = (p: Partial<DesignState>): void => dispatch({ type: "patch", patch: p });

  const applyDesignResult = async (res: ToolOperationResult, refreshProject: boolean): Promise<void> => {
    patch({
      designLoading: false,
      designError: res.success ? "" : res.message || "Operation failed.",
      designMessage: res.message,
      designResult: (res.data as Record<string, unknown> | null) ?? null,
    });
    if (refreshProject && res.success && res.project) {
      await onProjectMutated();
    }
  };

  const assignMaterial = async (inputs?: Partial<Pick<DesignState, "materialIdInput" | "materialSurfaceIdsCsv">>): Promise<void> => {
    if (!hasTauri) {
      patch({ designError: "Design authoring requires Tauri runtime." });
      return;
    }
    const materialId = (inputs?.materialIdInput ?? state.materialIdInput).trim();
    const surfaceIdsCsv = (inputs?.materialSurfaceIdsCsv ?? state.materialSurfaceIdsCsv).trim();
    if (!materialId) {
      patch({ designError: "Material id is required." });
      return;
    }
    if (!surfaceIdsCsv) {
      patch({ designError: "At least one surface id is required." });
      return;
    }
    patch({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("assign_material_in_project", {
        projectPath,
        materialId,
        surfaceIdsCsv,
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patch({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const addVariant = async (
    inputs?: Partial<Pick<DesignState, "variantIdInput" | "variantNameInput" | "variantDescriptionInput" | "variantDiffOpsJson">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ designError: "Variants require Tauri runtime." });
      return;
    }
    const variantId = (inputs?.variantIdInput ?? state.variantIdInput).trim();
    const variantName = (inputs?.variantNameInput ?? state.variantNameInput).trim();
    const variantDescription = (inputs?.variantDescriptionInput ?? state.variantDescriptionInput).trim();
    const variantDiffOpsJson = (inputs?.variantDiffOpsJson ?? state.variantDiffOpsJson).trim();
    if (!variantId || !variantName) {
      patch({ designError: "Variant id and name are required." });
      return;
    }
    if (variantDiffOpsJson) {
      try {
        const parsed = JSON.parse(variantDiffOpsJson);
        if (!Array.isArray(parsed)) {
          patch({ designError: "Variant diff JSON must be an array." });
          return;
        }
      } catch (err) {
        patch({ designError: err instanceof Error ? `Invalid variant diff JSON: ${err.message}` : "Invalid variant diff JSON." });
        return;
      }
    }
    patch({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("add_project_variant", {
        projectPath,
        variantId,
        name: variantName,
        description: variantDescription || null,
        diffOpsJson: variantDiffOpsJson || "[]",
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patch({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const compareVariants = async (
    inputs?: Partial<Pick<DesignState, "variantCompareJobId" | "variantCompareIdsCsv" | "variantCompareBaselineId">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ designError: "Variant comparison requires Tauri runtime." });
      return;
    }
    const variantCompareJobId = inputs?.variantCompareJobId ?? state.variantCompareJobId;
    const variantCompareIdsCsv = inputs?.variantCompareIdsCsv ?? state.variantCompareIdsCsv;
    const variantCompareBaselineId = inputs?.variantCompareBaselineId ?? state.variantCompareBaselineId;
    const jobId = (variantCompareJobId || selectedJobId).trim();
    if (!jobId) {
      patch({ designError: "Variant compare job id is required." });
      return;
    }
    if (!variantCompareIdsCsv.trim()) {
      patch({ designError: "Variant ids CSV is required." });
      return;
    }
    patch({ designLoading: true, designError: "", designMessage: "", designResult: null, variantVisualResult: null });
    try {
      const payload = await tauriInvoke<VariantVisualResponse>("compare_variants_visual", {
        projectPath,
        jobId,
        variantIdsCsv: variantCompareIdsCsv.trim(),
        baselineId: variantCompareBaselineId.trim() || null,
      });
      const rows: JsonRow[] = payload.variants.map((v) => ({
        id: v.id,
        name: v.name,
        mean_lux: v.metrics.mean_lux,
        uniformity: v.metrics.uniformity,
        ugr: v.metrics.ugr,
        fixture_count: v.metrics.fixture_count,
        compliant: v.compliant,
        error: v.error ?? "",
      }));
      patch({
        designLoading: false,
        designError: "",
        designMessage: `Compared ${payload.variants.length} variants.`,
        designResult: { rows },
        variantVisualResult: payload,
      });
    } catch (err) {
      patch({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const proposeOptimizations = async (
    inputs?: Partial<Pick<DesignState, "optimizationJobId" | "optimizationConstraintsJson" | "optimizationTopN">>,
  ): Promise<void> => {
    if (!hasTauri) {
      patch({ designError: "Optimization requires Tauri runtime." });
      return;
    }
    const optimizationJobId = inputs?.optimizationJobId ?? state.optimizationJobId;
    const optimizationConstraintsJson = inputs?.optimizationConstraintsJson ?? state.optimizationConstraintsJson;
    const optimizationTopN = inputs?.optimizationTopN ?? state.optimizationTopN;
    const jobId = (optimizationJobId || selectedJobId).trim();
    if (!jobId) {
      patch({ designError: "Optimization job id is required." });
      return;
    }
    let topN = Number(optimizationTopN);
    if (!Number.isFinite(topN) || topN < 1) {
      patch({ designError: "Optimization top N is invalid." });
      return;
    }
    topN = Math.round(topN);
    if (optimizationConstraintsJson.trim()) {
      try {
        const parsed = JSON.parse(optimizationConstraintsJson);
        if (parsed !== null && typeof parsed !== "object") {
          patch({ designError: "Optimization constraints must be a JSON object." });
          return;
        }
      } catch (err) {
        patch({
          designError: err instanceof Error ? `Invalid optimization constraints JSON: ${err.message}` : "Invalid optimization constraints JSON.",
        });
        return;
      }
    }
    patch({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("propose_project_optimizations", {
        projectPath,
        jobId,
        constraintsJson: optimizationConstraintsJson.trim() ? optimizationConstraintsJson.trim() : "{}",
        topN,
      });
      await applyDesignResult(res, false);
    } catch (err) {
      patch({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  const applyOptimizationOption = async (option: JsonRow | null): Promise<void> => {
    if (!hasTauri) {
      patch({ designError: "Optimization apply requires Tauri runtime." });
      return;
    }
    if (!option) {
      patch({ designError: "No optimization option selected." });
      return;
    }
    patch({ designLoading: true, designError: "", designMessage: "", designResult: null });
    try {
      const res = await tauriInvoke<ToolOperationResult>("apply_project_optimization_option", {
        projectPath,
        optionJson: JSON.stringify(option),
      });
      await applyDesignResult(res, true);
    } catch (err) {
      patch({ designLoading: false, designError: err instanceof Error ? err.message : String(err) });
    }
  };

  return {
    state,
    patch,
    assignMaterial,
    addVariant,
    compareVariants,
    proposeOptimizations,
    applyOptimizationOption,
  };
}
