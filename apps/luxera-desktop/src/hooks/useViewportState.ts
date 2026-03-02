import { useCallback, useReducer } from "react";
import type { BeamSpreadResponse, FalseColorGridResponse } from "../types";

interface SceneBounds3d {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

export interface ViewportState {
  falseColorData: FalseColorGridResponse | null;
  beamSpreadData: BeamSpreadResponse | null;
  falseColorOpacity: string;
  falseColorShowContours: boolean;
  falseColorShowValues: boolean;
  layerIsolux: boolean;
  isoluxLabelInterval: number;
  isoluxLevelCount: number;
  isoluxCustomLevels: string;
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
}

type Action = { type: "patch"; patch: Partial<ViewportState> };

function reducer(state: ViewportState, action: Action): ViewportState {
  switch (action.type) {
    case "patch": {
      let changed = false;
      for (const [key, value] of Object.entries(action.patch) as Array<[keyof ViewportState, ViewportState[keyof ViewportState]]>) {
        if (!Object.is(state[key], value)) {
          changed = true;
          break;
        }
      }
      if (!changed) {
        return state;
      }
      return { ...state, ...action.patch };
    }
    default:
      return state;
  }
}

export function useViewportState() {
  const [state, dispatch] = useReducer(reducer, {
    falseColorData: null,
    beamSpreadData: null,
    falseColorOpacity: "0.7",
    falseColorShowContours: true,
    falseColorShowValues: false,
    layerIsolux: false,
    isoluxLabelInterval: 2,
    isoluxLevelCount: 8,
    isoluxCustomLevels: "",
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
  });

  const patch = useCallback((p: Partial<ViewportState>): void => {
    dispatch({ type: "patch", patch: p });
  }, []);

  const resetSceneView = useCallback((sceneViewMode: "plan" | "3d", sceneBounds3d: SceneBounds3d | null): void => {
    if (sceneViewMode === "plan") {
      patch({ sceneZoom: 1, scenePanX: 0, scenePanY: 0 });
      return;
    }
    if (!sceneBounds3d) {
      patch({
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
    patch({
      sceneCamYawDeg: "38",
      sceneCamPitchDeg: "26",
      sceneCamDistance: (radius * 1.6).toFixed(3),
      sceneCamTargetX: tx.toFixed(3),
      sceneCamTargetY: ty.toFixed(3),
      sceneCamTargetZ: tz.toFixed(3),
    });
  }, [patch]);

  const startGridPlacement = useCallback((sceneViewMode: "plan" | "3d"): string | null => {
    if (sceneViewMode !== "plan") {
      return "Switch to plan view for click-to-place.";
    }
    patch({ placementMode: "grid" });
    return null;
  }, [patch]);

  return {
    state,
    patch,
    resetSceneView,
    startGridPlacement,
  };
}
