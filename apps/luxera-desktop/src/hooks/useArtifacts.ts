import { useState } from "react";
import type { ArtifactBinaryRead, ArtifactEntry, ArtifactRead } from "../types";
import { tauriInvoke } from "../utils/tauri";

interface UseArtifactsArgs {
  hasTauri: boolean;
}

export function useArtifacts({ hasTauri }: UseArtifactsArgs) {
  const [artifactPath, setArtifactPath] = useState("");
  const [artifact, setArtifact] = useState<ArtifactRead | null>(null);
  const [artifactBinary, setArtifactBinary] = useState<ArtifactBinaryRead | null>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactBinaryLoading, setArtifactBinaryLoading] = useState(false);
  const [artifactError, setArtifactError] = useState("");
  const [artifactList, setArtifactList] = useState<ArtifactEntry[]>([]);
  const [artifactListLoading, setArtifactListLoading] = useState(false);
  const [artifactListError, setArtifactListError] = useState("");
  const [selectedArtifactPath, setSelectedArtifactPath] = useState("");

  const loadArtifactInventory = async (resultDir: string): Promise<void> => {
    if (!hasTauri || !resultDir.trim()) {
      return;
    }
    setArtifactListLoading(true);
    setArtifactListError("");
    try {
      const artifacts = await tauriInvoke<ArtifactEntry[]>("list_result_artifacts", { resultDir, limit: 500 });
      setArtifactList(artifacts);
      setSelectedArtifactPath(artifacts.length > 0 ? artifacts[0].path : "");
      setArtifactListLoading(false);
    } catch (err) {
      setArtifactListLoading(false);
      setArtifactListError(err instanceof Error ? err.message : String(err));
    }
  };

  const readArtifactAtPath = async (path: string): Promise<void> => {
    if (!hasTauri) {
      setArtifactError("Artifact reading requires Tauri runtime.");
      return;
    }
    const cleanPath = path.trim();
    if (!cleanPath) {
      setArtifactError("Artifact path is empty.");
      return;
    }
    setArtifactLoading(true);
    setArtifactError("");
    setArtifact(null);
    try {
      const payload = await tauriInvoke<ArtifactRead>("read_artifact", { path: cleanPath, maxBytes: null });
      setArtifact(payload);
      setArtifactLoading(false);
    } catch (err) {
      setArtifactLoading(false);
      setArtifactError(err instanceof Error ? err.message : String(err));
    }
  };

  const readArtifactBinaryAtPath = async (path: string): Promise<void> => {
    if (!hasTauri) {
      setArtifactError("Artifact preview requires Tauri runtime.");
      return;
    }
    const cleanPath = path.trim();
    if (!cleanPath) {
      setArtifactError("Artifact path is empty.");
      return;
    }
    setArtifactBinaryLoading(true);
    setArtifactError("");
    setArtifactBinary(null);
    try {
      const isPdf = cleanPath.toLowerCase().endsWith(".pdf");
      const payload = await tauriInvoke<ArtifactBinaryRead>("read_artifact_binary", {
        path: cleanPath,
        maxBytes: isPdf ? 10_000_000 : null,
      });
      setArtifactBinary(payload);
      setArtifactBinaryLoading(false);
    } catch (err) {
      setArtifactBinaryLoading(false);
      setArtifactError(err instanceof Error ? err.message : String(err));
    }
  };

  const readArtifact = async (): Promise<void> => {
    await readArtifactAtPath(artifactPath);
  };

  const readSelectedArtifact = async (): Promise<void> => {
    if (!selectedArtifactPath) {
      setArtifactError("No artifact selected.");
      return;
    }
    setArtifactPath(selectedArtifactPath);
    await readArtifactAtPath(selectedArtifactPath);
  };

  const previewSelectedArtifact = async (): Promise<void> => {
    if (!selectedArtifactPath) {
      setArtifactError("No artifact selected.");
      return;
    }
    setArtifactPath(selectedArtifactPath);
    await readArtifactBinaryAtPath(selectedArtifactPath);
  };

  const primeArtifactPath = (path: string): void => {
    setArtifactPath(path);
  };

  return {
    artifactPath,
    setArtifactPath,
    artifact,
    artifactBinary,
    artifactLoading,
    artifactBinaryLoading,
    artifactError,
    artifactList,
    artifactListLoading,
    artifactListError,
    selectedArtifactPath,
    setSelectedArtifactPath,
    loadArtifactInventory,
    readArtifactAtPath,
    readArtifactBinaryAtPath,
    readArtifact,
    readSelectedArtifact,
    previewSelectedArtifact,
    primeArtifactPath,
  };
}
