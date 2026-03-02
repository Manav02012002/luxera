use base64::engine::general_purpose;
use base64::Engine as _;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::SystemTime;
use tauri::Manager;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopResultBundle {
    source_dir: String,
    result: Value,
    tables: Value,
    results: Value,
    road_summary: Value,
    roadway_submission: Value,
    warnings: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RecentRun {
    result_dir: String,
    modified_unix_s: u64,
    job_id: Option<String>,
    job_type: Option<String>,
    contract_version: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ArtifactRead {
    path: String,
    size_bytes: u64,
    truncated: bool,
    content: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ArtifactBinaryRead {
    path: String,
    size_bytes: u64,
    truncated: bool,
    mime_type: String,
    data_base64: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ArtifactEntry {
    path: String,
    relative_path: String,
    size_bytes: u64,
    modified_unix_s: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectJob {
    id: String,
    job_type: String,
    backend: String,
    seed: i64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectJobsResponse {
    project_path: String,
    project_name: Option<String>,
    jobs: Vec<ProjectJob>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectDocument {
    path: String,
    name: String,
    schema_version: i64,
    job_count: usize,
    content: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectValidationResult {
    valid: bool,
    project_name: Option<String>,
    schema_version: Option<i64>,
    checked_jobs: usize,
    errors: Vec<String>,
    warnings: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GeometryOperationResult {
    success: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    project: Option<ProjectDocument>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExportOperationResult {
    success: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    output_path: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct AgentRuntimeResult {
    response: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ToolOperationResult {
    success: bool,
    message: String,
    data: Value,
    project: Option<ProjectDocument>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PhotometryVerifyResponse {
    ok: bool,
    error: Option<String>,
    result: Option<Value>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct FalseColorGridResponse {
    grids: Vec<Value>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct JobRunResponse {
    project_path: String,
    job_id: String,
    success: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    result_dir: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct JobRunStartResponse {
    run_id: u64,
    project_path: String,
    job_id: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct JobRunPollResponse {
    run_id: u64,
    done: bool,
    success: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    result_dir: Option<String>,
}

struct RunningJob {
    child: Child,
    stdout_buf: Arc<Mutex<String>>,
    stderr_buf: Arc<Mutex<String>>,
}

fn running_jobs() -> &'static Mutex<HashMap<u64, RunningJob>> {
    static RUNS: OnceLock<Mutex<HashMap<u64, RunningJob>>> = OnceLock::new();
    RUNS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn next_run_id() -> u64 {
    static RUN_ID: AtomicU64 = AtomicU64::new(1);
    RUN_ID.fetch_add(1, Ordering::Relaxed)
}

fn read_json_file(path: &Path, warnings: &mut Vec<String>) -> Value {
    if !path.exists() {
        warnings.push(format!("Missing file: {}", path.display()));
        return Value::Null;
    }
    match fs::read_to_string(path) {
        Ok(raw) => match serde_json::from_str::<Value>(&raw) {
            Ok(value) => value,
            Err(err) => {
                warnings.push(format!("Invalid JSON in {}: {}", path.display(), err));
                Value::Null
            }
        },
        Err(err) => {
            warnings.push(format!("Unable to read {}: {}", path.display(), err));
            Value::Null
        }
    }
}

fn read_optional_json_file(path: &Path, warnings: &mut Vec<String>) -> Value {
    if !path.exists() {
        return Value::Null;
    }
    match fs::read_to_string(path) {
        Ok(raw) => match serde_json::from_str::<Value>(&raw) {
            Ok(value) => value,
            Err(err) => {
                warnings.push(format!("Invalid JSON in {}: {}", path.display(), err));
                Value::Null
            }
        },
        Err(err) => {
            warnings.push(format!("Unable to read {}: {}", path.display(), err));
            Value::Null
        }
    }
}

fn find_repo_root(start: &Path) -> Option<PathBuf> {
    let mut cursor = Some(start);
    while let Some(path) = cursor {
        let marker = path.join("pyproject.toml");
        if marker.exists() {
            return Some(path.to_path_buf());
        }
        cursor = path.parent();
    }
    None
}

fn resolve_repo_relative(path: &Path, cwd: &Path) -> Result<PathBuf, String> {
    if path.is_absolute() {
        return Ok(path.to_path_buf());
    }
    let repo_root = find_repo_root(cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    Ok(repo_root.join(path))
}

fn resolve_python_executable() -> String {
    if let Ok(py) = std::env::var("PYTHON") {
        let trimmed = py.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }
    "python3".to_string()
}

fn parse_result_dir(stdout: &str, stderr: &str) -> Option<String> {
    for line in stdout.lines().chain(stderr.lines()) {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("Result dir:") {
            let d = rest.trim();
            if !d.is_empty() {
                return Some(d.to_string());
            }
        }
    }
    None
}

fn run_python_json(args: &[String]) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let repo_root = find_repo_root(&cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    let python = resolve_python_executable();
    let output = Command::new(&python)
        .args(args)
        .current_dir(&repo_root)
        .output()
        .map_err(|e| format!("Failed to execute Python via {}: {}", python, e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    if !output.status.success() {
        return Err(format!(
            "Python command failed (exit {}): {}",
            output.status.code().unwrap_or(-1),
            if stderr.trim().is_empty() { stdout.trim() } else { stderr.trim() }
        ));
    }
    serde_json::from_str::<Value>(stdout.trim()).map_err(|e| format!("Invalid JSON from Python: {}", e))
}

fn run_luxera_cli(args: &[String]) -> Result<(bool, i32, String, String), String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let repo_root = find_repo_root(&cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    let python = resolve_python_executable();
    let mut cmd_args = vec!["-m".to_string(), "luxera.cli".to_string()];
    cmd_args.extend_from_slice(args);
    let output = Command::new(&python)
        .args(&cmd_args)
        .current_dir(&repo_root)
        .output()
        .map_err(|e| format!("Failed to execute Luxera CLI via {}: {}", python, e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let success = output.status.success();
    let exit_code = output.status.code().unwrap_or(-1);
    Ok((success, exit_code, stdout, stderr))
}

fn spawn_stream_reader<R: std::io::Read + Send + 'static>(reader: R, dst: Arc<Mutex<String>>) {
    thread::spawn(move || {
        let mut br = BufReader::new(reader);
        let mut line = String::new();
        loop {
            line.clear();
            match br.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    if let Ok(mut out) = dst.lock() {
                        out.push_str(&line);
                    }
                }
                Err(_) => break,
            }
        }
    });
}

fn latest_result_dir_from_out(out_dir: &Path) -> Option<PathBuf> {
    if !out_dir.exists() {
        return None;
    }
    let mut candidates: Vec<(SystemTime, PathBuf)> = Vec::new();
    let entries = fs::read_dir(out_dir).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let result_json = path.join("result.json");
        if !result_json.exists() {
            continue;
        }
        let modified = fs::metadata(&result_json)
            .and_then(|m| m.modified())
            .unwrap_or(SystemTime::UNIX_EPOCH);
        candidates.push((modified, path));
    }
    candidates.sort_by(|a, b| b.0.cmp(&a.0));
    candidates.first().map(|(_, path)| path.clone())
}

fn run_modified_unix_seconds(path: &Path) -> u64 {
    fs::metadata(path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn collect_artifacts(root: &Path, cursor: &Path, out: &mut Vec<ArtifactEntry>) -> Result<(), String> {
    let entries = fs::read_dir(cursor).map_err(|e| format!("Failed to scan {}: {}", cursor.display(), e))?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_artifacts(root, &path, out)?;
            continue;
        }
        if !path.is_file() {
            continue;
        }
        let meta = fs::metadata(&path).map_err(|e| format!("Cannot stat {}: {}", path.display(), e))?;
        let rel = path
            .strip_prefix(root)
            .unwrap_or(&path)
            .to_string_lossy()
            .to_string();
        out.push(ArtifactEntry {
            path: path.to_string_lossy().to_string(),
            relative_path: rel,
            size_bytes: meta.len(),
            modified_unix_s: run_modified_unix_seconds(&path),
        });
    }
    Ok(())
}

fn recent_projects_store_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Cannot resolve app data directory: {}", e))?;
    fs::create_dir_all(&dir).map_err(|e| format!("Cannot create app data directory {}: {}", dir.display(), e))?;
    Ok(dir.join("recent_projects.json"))
}

fn mime_for_path(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|x| x.to_str())
        .map(|x| x.to_ascii_lowercase())
        .as_deref()
    {
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        Some("gif") => "image/gif",
        Some("svg") => "image/svg+xml",
        Some("pdf") => "application/pdf",
        _ => "application/octet-stream",
    }
}

#[tauri::command]
fn load_recent_projects_store(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    let path = recent_projects_store_path(&app)?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let raw = fs::read_to_string(&path).map_err(|e| format!("Cannot read {}: {}", path.display(), e))?;
    let payload: Value =
        serde_json::from_str(&raw).map_err(|e| format!("Invalid recent-projects JSON {}: {}", path.display(), e))?;
    let projects = payload
        .get("recent_projects")
        .and_then(|x| x.as_array())
        .map(|arr| {
            let mut out: Vec<String> = Vec::new();
            for row in arr {
                if let Some(path) = row.as_str() {
                    let clean = path.trim();
                    if clean.is_empty() {
                        continue;
                    }
                    if !out.iter().any(|v| v == clean) {
                        out.push(clean.to_string());
                    }
                }
            }
            out
        })
        .unwrap_or_default();
    Ok(projects)
}

#[tauri::command]
fn save_recent_projects_store(app: tauri::AppHandle, projects: Vec<String>) -> Result<bool, String> {
    let path = recent_projects_store_path(&app)?;
    let mut sanitized: Vec<String> = Vec::new();
    for project in projects {
        let clean = project.trim();
        if clean.is_empty() {
            continue;
        }
        if !sanitized.iter().any(|v| v == clean) {
            sanitized.push(clean.to_string());
        }
        if sanitized.len() >= 50 {
            break;
        }
    }
    let updated_unix_s = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let payload = json!({
        "recent_projects": sanitized,
        "updated_unix_s": updated_unix_s,
    });
    let text = serde_json::to_string_pretty(&payload).map_err(|e| format!("Cannot encode recent-projects payload: {}", e))?;
    fs::write(&path, text).map_err(|e| format!("Cannot write {}: {}", path.display(), e))?;
    Ok(true)
}

#[tauri::command]
fn load_backend_outputs(result_dir: Option<String>) -> Result<DesktopResultBundle, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let source_dir = if let Some(dir) = result_dir {
        let trimmed = dir.trim();
        if trimmed.is_empty() {
            return Err("Result directory is empty".to_string());
        }
        PathBuf::from(trimmed)
    } else {
        let repo_root = find_repo_root(&cwd).ok_or_else(|| {
            "Could not locate repository root (pyproject.toml) from current directory".to_string()
        })?;
        let out_dir = repo_root.join("out");
        latest_result_dir_from_out(&out_dir)
            .ok_or_else(|| format!("No result.json found under {}", out_dir.display()))?
    };

    let mut warnings: Vec<String> = Vec::new();
    let result = read_json_file(&source_dir.join("result.json"), &mut warnings);
    let tables = read_json_file(&source_dir.join("tables.json"), &mut warnings);
    let results = read_json_file(&source_dir.join("results.json"), &mut warnings);
    let road_summary = read_optional_json_file(&source_dir.join("road_summary.json"), &mut warnings);
    let roadway_submission = read_optional_json_file(&source_dir.join("roadway_submission.json"), &mut warnings);

    Ok(DesktopResultBundle {
        source_dir: source_dir.to_string_lossy().to_string(),
        result,
        tables,
        results,
        road_summary,
        roadway_submission,
        warnings,
    })
}

#[tauri::command]
fn get_falsecolor_grid_data(
    result_dir: String,
    grid_name: Option<String>,
    contour_level_count: Option<i64>,
    contour_custom_levels_csv: Option<String>,
) -> Result<FalseColorGridResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_path = PathBuf::from(result_dir.trim());
    if raw_path.as_os_str().is_empty() {
        return Err("Result directory path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw_path, &cwd)?;
    if !resolved.exists() || !resolved.is_dir() {
        return Err(format!("Directory not found: {}", resolved.display()));
    }
    let selected_grid = grid_name.unwrap_or_default().trim().to_string();
    let contour_level_count = contour_level_count.unwrap_or(8).clamp(4, 20);
    let contour_custom_levels_csv = contour_custom_levels_csv.unwrap_or_default();
    let script = r##"
import json
import math
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

from luxera.viz.contours import compute_contour_levels


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip())
    return clean.strip("_") or "grid"


def _hex_from_rgba(rgba) -> str:
    r = int(max(0, min(255, round(float(rgba[0]) * 255.0))))
    g = int(max(0, min(255, round(float(rgba[1]) * 255.0))))
    b = int(max(0, min(255, round(float(rgba[2]) * 255.0))))
    return f"#{r:02x}{g:02x}{b:02x}"


def _load_grid_csv_values(result_dir: Path, row: dict) -> tuple[np.ndarray | None, np.ndarray | None]:
    candidates = []
    gid = str(row.get("id", "")).strip()
    gname = str(row.get("name", "")).strip()
    if gid:
        candidates.append(result_dir / f"grid_{gid}.csv")
    if gname:
        candidates.append(result_dir / f"grid_{_slug(gname)}.csv")
    candidates.append(result_dir / "grid.csv")
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        try:
            data = np.loadtxt(path, delimiter=",", skiprows=1)
            if data.ndim == 1:
                data = np.asarray(data, dtype=float).reshape(1, -1)
            if data.shape[1] < 4:
                continue
            points = np.asarray(data[:, :3], dtype=float)
            values = np.asarray(data[:, 3], dtype=float).reshape(-1)
            return values, points
        except Exception:
            continue
    return None, None


def _extract_values_and_points(result_dir: Path, row: dict) -> tuple[np.ndarray, np.ndarray | None]:
    if isinstance(row.get("cells"), list):
        cells = row.get("cells")
        vals = []
        for cell in cells:
            if isinstance(cell, dict):
                if "lux" in cell:
                    vals.append(_to_float(cell.get("lux"), 0.0))
            else:
                vals.append(_to_float(cell, 0.0))
        if vals:
            return np.asarray(vals, dtype=float).reshape(-1), None
    for key in ("lux_values", "values", "grid_values", "lux"):
        if isinstance(row.get(key), list):
            return np.asarray([_to_float(v, 0.0) for v in row.get(key)], dtype=float).reshape(-1), None
    values, points = _load_grid_csv_values(result_dir, row)
    if values is not None:
        return values, points
    raise ValueError(f"Grid '{row.get('name', row.get('id', 'unknown'))}' has no per-point lux values")


def _infer_dims(nx: int, ny: int, n: int) -> tuple[int, int]:
    if nx > 0 and ny > 0:
        return nx, ny
    if nx > 0 and ny <= 0 and n % nx == 0:
        return nx, n // nx
    if ny > 0 and nx <= 0 and n % ny == 0:
        return n // ny, ny
    side = int(round(math.sqrt(n)))
    if side > 0 and side * side == n:
        return side, side
    return n, 1


def _origin_wh_elev(row: dict, points: np.ndarray | None, nx: int, ny: int) -> tuple[list[float], float, float, float]:
    origin_raw = row.get("origin")
    if isinstance(origin_raw, (list, tuple)) and len(origin_raw) >= 3:
        ox, oy, oz = _to_float(origin_raw[0]), _to_float(origin_raw[1]), _to_float(origin_raw[2])
    else:
        ox = oy = oz = 0.0
    width = _to_float(row.get("width"), 0.0)
    height = _to_float(row.get("height"), 0.0)
    elevation = _to_float(row.get("elevation"), oz)
    if points is not None and points.size > 0:
        px = np.asarray(points[:, 0], dtype=float)
        py = np.asarray(points[:, 1], dtype=float)
        pz = np.asarray(points[:, 2], dtype=float)
        pminx = float(np.min(px))
        pmaxx = float(np.max(px))
        pminy = float(np.min(py))
        pmaxy = float(np.max(py))
        ox = pminx if width <= 0 else ox
        oy = pminy if height <= 0 else oy
        if width <= 0:
            width = max(0.0, pmaxx - pminx)
        if height <= 0:
            height = max(0.0, pmaxy - pminy)
        if not np.isnan(pz).all():
            elevation = float(np.nanmean(pz))
            oz = elevation
    if nx > 1 and width <= 0:
        width = float(nx - 1)
    if ny > 1 and height <= 0:
        height = float(ny - 1)
    return [float(ox), float(oy), float(oz)], float(width), float(height), float(elevation)


def _build_contours(
    values: np.ndarray,
    origin: list[float],
    width: float,
    height: float,
    nx: int,
    ny: int,
    level_count: int,
    custom_levels: list[float],
) -> list[dict]:
    if nx < 2 or ny < 2:
        return []
    z = values.reshape(ny, nx)
    levels = [float(v) for v in custom_levels if np.isfinite(v)] if custom_levels else compute_contour_levels(z, n_levels=int(level_count))
    if not levels:
        return []
    x = np.linspace(float(origin[0]), float(origin[0]) + float(width), nx)
    y = np.linspace(float(origin[1]), float(origin[1]) + float(height), ny)
    X, Y = np.meshgrid(x, y)
    fig, ax = plt.subplots()
    try:
        cs = ax.contour(X, Y, z, levels=levels)
        contours = []
        for i, level in enumerate(cs.levels):
            paths = []
            if i < len(cs.allsegs):
                for seg in cs.allsegs[i]:
                    arr = np.asarray(seg, dtype=float)
                    if arr.ndim == 2 and arr.shape[0] >= 2 and arr.shape[1] >= 2:
                        paths.append(arr[:, :2].tolist())
            contours.append({"level": float(level), "paths": paths})
        return contours
    finally:
        plt.close(fig)


def main() -> None:
    result_dir = Path(sys.argv[1]).expanduser().resolve()
    selected = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
    level_count = int(float(sys.argv[3])) if len(sys.argv) > 3 and str(sys.argv[3]).strip() else 8
    level_count = max(4, min(20, level_count))
    custom_levels_raw = (sys.argv[4] if len(sys.argv) > 4 else "").strip()
    custom_levels = []
    if custom_levels_raw:
        for token in custom_levels_raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                custom_levels.append(float(token))
            except Exception:
                continue
    if custom_levels:
        custom_levels = sorted(set(custom_levels))
    result_json = _load_json(result_dir / "result.json")
    tables_json = _load_json(result_dir / "tables.json")

    # Load metadata eagerly (contract requirement) even if not directly emitted.
    _job = result_json.get("job", {})
    _summary = result_json.get("summary", {})

    rows = tables_json.get("grids", [])
    if not isinstance(rows, list):
        rows = []

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("id") or "grid")
        gid = str(row.get("id") or "")
        if selected and selected not in (name, gid):
            continue
        values, points = _extract_values_and_points(result_dir, row)
        nx = _to_int(row.get("nx"), 0)
        ny = _to_int(row.get("ny"), 0)
        nx, ny = _infer_dims(nx, ny, int(values.size))
        if nx * ny != int(values.size):
            raise ValueError(f"Grid '{name}' has {values.size} values but nx*ny={nx*ny}")
        origin, width, height, elevation = _origin_wh_elev(row, points, nx, ny)
        vmin = float(np.min(values)) if values.size else 0.0
        vmax = float(np.max(values)) if values.size else 0.0
        vavg = float(np.mean(values)) if values.size else 0.0
        u0 = (vmin / vavg) if abs(vavg) > 1e-12 else 0.0
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax) if vmax > vmin else mcolors.Normalize(vmin=vmin - 1.0, vmax=vmin + 1.0)
        cmap = cm.get_cmap("inferno")
        cells = [{"lux": float(v), "color": _hex_from_rgba(cmap(norm(float(v))))} for v in values.tolist()]
        contours = _build_contours(values, origin, width, height, nx, ny, level_count, custom_levels)
        out.append(
            {
                "name": name,
                "origin": [float(origin[0]), float(origin[1]), float(origin[2])],
                "width": float(width),
                "height": float(height),
                "nx": int(nx),
                "ny": int(ny),
                "elevation": float(elevation),
                "cells": cells,
                "stats": {"min": vmin, "max": vmax, "avg": vavg, "u0": float(u0)},
                "contours": contours,
            }
        )
    print(json.dumps({"grids": out}))


if __name__ == "__main__":
    main()
"##;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        resolved.to_string_lossy().to_string(),
        selected_grid,
        contour_level_count.to_string(),
        contour_custom_levels_csv,
    ])?;
    let grids = payload
        .get("grids")
        .and_then(|x| x.as_array())
        .cloned()
        .unwrap_or_default();
    Ok(FalseColorGridResponse { grids })
}

#[tauri::command]
fn list_project_jobs(project_path: String) -> Result<ProjectJobsResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    let raw_json = fs::read_to_string(&resolved).map_err(|e| format!("Cannot read {}: {}", resolved.display(), e))?;
    let root: Value =
        serde_json::from_str(&raw_json).map_err(|e| format!("Invalid project JSON {}: {}", resolved.display(), e))?;
    let project_name = root.get("name").and_then(|x| x.as_str()).map(|x| x.to_string());
    let mut jobs: Vec<ProjectJob> = Vec::new();
    let arr = root
        .get("jobs")
        .and_then(|x| x.as_array())
        .ok_or_else(|| format!("Project {} has no 'jobs' array", resolved.display()))?;
    for row in arr {
        let Some(obj) = row.as_object() else {
            continue;
        };
        let Some(id) = obj.get("id").and_then(|x| x.as_str()) else {
            continue;
        };
        let job_type = obj
            .get("type")
            .and_then(|x| x.as_str())
            .unwrap_or("unknown")
            .to_string();
        let backend = obj
            .get("backend")
            .and_then(|x| x.as_str())
            .unwrap_or("cpu")
            .to_string();
        let seed = obj.get("seed").and_then(|x| x.as_i64()).unwrap_or(0);
        jobs.push(ProjectJob {
            id: id.to_string(),
            job_type,
            backend,
            seed,
        });
    }
    Ok(ProjectJobsResponse {
        project_path: resolved.to_string_lossy().to_string(),
        project_name,
        jobs,
    })
}

#[tauri::command]
fn init_project_file(project_path: String, name: Option<String>) -> Result<ProjectDocument, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    if let Some(parent) = resolved.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }

    let resolved_project = resolved.to_string_lossy().to_string();
    let mut init_cmd = vec![
        "-m".to_string(),
        "luxera.cli".to_string(),
        "init".to_string(),
        resolved_project.clone(),
    ];
    let owned_name = name.unwrap_or_default();
    if !owned_name.trim().is_empty() {
        init_cmd.push("--name".to_string());
        init_cmd.push(owned_name.trim().to_string());
    }
    let python = resolve_python_executable();
    let output = Command::new(&python)
        .args(&init_cmd)
        .output()
        .map_err(|e| format!("Failed to run init command via {}: {}", python, e))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        return Err(format!(
            "Project init failed: {}",
            if stderr.trim().is_empty() { stdout.trim() } else { stderr.trim() }
        ));
    }
    open_project_file(resolved.to_string_lossy().to_string())
}

#[tauri::command]
fn open_project_file(project_path: String) -> Result<ProjectDocument, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    let content = fs::read_to_string(&resolved).map_err(|e| format!("Cannot read {}: {}", resolved.display(), e))?;
    let root: Value =
        serde_json::from_str(&content).map_err(|e| format!("Invalid project JSON {}: {}", resolved.display(), e))?;
    let name = root
        .get("name")
        .and_then(|x| x.as_str())
        .unwrap_or(resolved.file_stem().and_then(|x| x.to_str()).unwrap_or("project"))
        .to_string();
    let schema_version = root.get("schema_version").and_then(|x| x.as_i64()).unwrap_or(0);
    let job_count = root.get("jobs").and_then(|x| x.as_array()).map(|x| x.len()).unwrap_or(0);
    Ok(ProjectDocument {
        path: resolved.to_string_lossy().to_string(),
        name,
        schema_version,
        job_count,
        content,
    })
}

#[tauri::command]
fn save_project_file(project_path: String, content: String) -> Result<ProjectDocument, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    if let Some(parent) = resolved.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }
    serde_json::from_str::<Value>(&content).map_err(|e| format!("Invalid JSON: {}", e))?;
    fs::write(&resolved, content).map_err(|e| format!("Cannot write {}: {}", resolved.display(), e))?;
    open_project_file(resolved.to_string_lossy().to_string())
}

#[tauri::command]
fn validate_project_file(project_path: String, job_id: Option<String>) -> Result<ProjectValidationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    if !resolved.exists() || !resolved.is_file() {
        return Err(format!("Project file not found: {}", resolved.display()));
    }

    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema
from luxera.project.validator import validate_project_for_job
path = Path(sys.argv[1])
job_id = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
errors = []
warnings = []
checked = 0
project_name = None
schema_version = None
try:
    project = load_project_schema(path)
    project_name = getattr(project, "name", None)
    schema_version = int(getattr(project, "schema_version", 0))
    jobs = list(getattr(project, "jobs", []) or [])
    if job_id:
        jobs = [j for j in jobs if getattr(j, "id", "") == job_id]
        if not jobs:
            errors.append(f"job not found: {job_id}")
    if not jobs:
        warnings.append("project has no jobs to validate")
    for j in jobs:
        checked += 1
        try:
            validate_project_for_job(project, j)
        except Exception as e:
            errors.append(f"{getattr(j,'id','<unknown>')}: {e}")
except Exception as e:
    errors.append(str(e))
out = {
    'valid': len(errors) == 0,
    'project_name': project_name,
    'schema_version': schema_version,
    'checked_jobs': checked,
    'errors': errors,
    'warnings': warnings,
}
print(json.dumps(out))
"#;
    let mut args: Vec<String> = vec![
        "-c".to_string(),
        script.to_string(),
        resolved.to_string_lossy().to_string(),
    ];
    let owned_job = job_id.unwrap_or_default();
    if !owned_job.trim().is_empty() {
        args.push(owned_job.trim().to_string());
    }
    let payload = run_python_json(&args)?;
    let valid = payload.get("valid").and_then(|x| x.as_bool()).unwrap_or(false);
    let project_name = payload.get("project_name").and_then(|x| x.as_str()).map(|x| x.to_string());
    let schema_version = payload.get("schema_version").and_then(|x| x.as_i64());
    let checked_jobs = payload.get("checked_jobs").and_then(|x| x.as_u64()).unwrap_or(0) as usize;
    let errors = payload
        .get("errors")
        .and_then(|x| x.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect::<Vec<String>>()
        })
        .unwrap_or_default();
    let warnings = payload
        .get("warnings")
        .and_then(|x| x.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect::<Vec<String>>()
        })
        .unwrap_or_default();
    Ok(ProjectValidationResult {
        valid,
        project_name,
        schema_version,
        checked_jobs,
        errors,
        warnings,
    })
}

#[tauri::command]
fn add_room_to_project(
    project_path: String,
    name: Option<String>,
    width: f64,
    length: f64,
    height: f64,
    origin_x: Option<f64>,
    origin_y: Option<f64>,
    origin_z: Option<f64>,
    floor_reflectance: Option<f64>,
    wall_reflectance: Option<f64>,
    ceiling_reflectance: Option<f64>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw = PathBuf::from(project_path.trim());
    if raw.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw, &cwd)?;
    let mut args = vec![
        "add-room".to_string(),
        resolved.to_string_lossy().to_string(),
        "--width".to_string(),
        width.to_string(),
        "--length".to_string(),
        length.to_string(),
        "--height".to_string(),
        height.to_string(),
        "--origin-x".to_string(),
        origin_x.unwrap_or(0.0).to_string(),
        "--origin-y".to_string(),
        origin_y.unwrap_or(0.0).to_string(),
        "--origin-z".to_string(),
        origin_z.unwrap_or(0.0).to_string(),
        "--floor-reflectance".to_string(),
        floor_reflectance.unwrap_or(0.2).to_string(),
        "--wall-reflectance".to_string(),
        wall_reflectance.unwrap_or(0.5).to_string(),
        "--ceiling-reflectance".to_string(),
        ceiling_reflectance.unwrap_or(0.7).to_string(),
    ];
    if let Some(n) = name {
        if !n.trim().is_empty() {
            args.push("--name".to_string());
            args.push(n.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn import_geometry_to_project(
    project_path: String,
    file_path: String,
    format: Option<String>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let raw_file = PathBuf::from(file_path.trim());
    if raw_file.as_os_str().is_empty() {
        return Err("Geometry file path is empty".to_string());
    }
    let resolved_file = resolve_repo_relative(&raw_file, &cwd)?;
    let mut args = vec![
        "geometry".to_string(),
        "import".to_string(),
        resolved_project.to_string_lossy().to_string(),
        resolved_file.to_string_lossy().to_string(),
    ];
    if let Some(fmt) = format {
        if !fmt.trim().is_empty() {
            args.push("--format".to_string());
            args.push(fmt.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn clean_geometry_in_project(
    project_path: String,
    snap_tolerance: Option<f64>,
    merge_coplanar: Option<bool>,
    detect_rooms: Option<bool>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let mut args = vec![
        "geometry".to_string(),
        "clean".to_string(),
        resolved_project.to_string_lossy().to_string(),
        "--snap-tolerance".to_string(),
        snap_tolerance.unwrap_or(1e-3).to_string(),
    ];
    if detect_rooms.unwrap_or(false) {
        args.push("--detect-rooms".to_string());
    }
    if !merge_coplanar.unwrap_or(true) {
        args.push("--no-merge".to_string());
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn add_photometry_to_project(
    project_path: String,
    file_path: String,
    asset_id: Option<String>,
    format: Option<String>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let raw_file = PathBuf::from(file_path.trim());
    if raw_file.as_os_str().is_empty() {
        return Err("Photometry file path is empty".to_string());
    }
    let resolved_file = resolve_repo_relative(&raw_file, &cwd)?;

    let mut args = vec![
        "add-photometry".to_string(),
        resolved_project.to_string_lossy().to_string(),
        resolved_file.to_string_lossy().to_string(),
    ];
    if let Some(v) = asset_id {
        if !v.trim().is_empty() {
            args.push("--id".to_string());
            args.push(v.trim().to_string());
        }
    }
    if let Some(v) = format {
        if !v.trim().is_empty() {
            args.push("--format".to_string());
            args.push(v.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn verify_photometry_file_input(
    file_path: String,
    format: Option<String>,
) -> Result<PhotometryVerifyResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_file = PathBuf::from(file_path.trim());
    if raw_file.as_os_str().is_empty() {
        return Err("Photometry file path is empty".to_string());
    }
    let resolved_file = resolve_repo_relative(&raw_file, &cwd)?;
    let script = r#"
import json, sys
from luxera.photometry.verify import verify_photometry_file
fpath = sys.argv[1]
fmt = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
try:
    result = verify_photometry_file(fpath, fmt=fmt).to_dict()
    print(json.dumps({"ok": True, "error": None, "result": result}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "result": None}))
"#;
    let fmt = format.unwrap_or_default().trim().to_string();
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        resolved_file.to_string_lossy().to_string(),
        fmt,
    ])?;
    let ok = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let error = payload
        .get("error")
        .and_then(|x| x.as_str())
        .map(|x| x.to_string());
    let result = payload.get("result").cloned();
    Ok(PhotometryVerifyResponse { ok, error, result })
}

#[tauri::command]
fn verify_project_photometry_asset(
    project_path: String,
    asset_id: String,
) -> Result<PhotometryVerifyResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    if asset_id.trim().is_empty() {
        return Err("Asset id is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema
from luxera.photometry.verify import verify_photometry_file
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
project_path = Path(sys.argv[1]).expanduser().resolve()
asset_id = sys.argv[2].strip()
project = load_project_schema(project_path)
asset = next((a for a in project.photometry_assets if a.id == asset_id), None)
if asset is None:
    print(json.dumps({"ok": False, "error": f"Photometry asset not found: {asset_id}", "result": None}))
elif not asset.path:
    print(json.dumps({"ok": False, "error": f"Photometry asset has no file path: {asset_id}", "result": None}))
else:
    apath = Path(asset.path).expanduser()
    if not apath.is_absolute():
        apath = (project_path.parent / apath).resolve()
    try:
        result = verify_photometry_file(str(apath), fmt=asset.format).to_dict()
        raw = apath.read_text(encoding="utf-8", errors="replace")
        fmt = str(asset.format or "").upper()
        if fmt == "IES":
            phot = photometry_from_parsed_ies(parse_ies_text(raw, source_path=apath))
        elif fmt == "LDT":
            phot = photometry_from_parsed_ldt(parse_ldt_text(raw))
        else:
            phot = None
        if phot is not None and len(phot.c_angles_deg) > 0 and len(phot.gamma_angles_deg) > 0:
            c_angles = [float(x) for x in phot.c_angles_deg]
            g_angles = [float(x) for x in phot.gamma_angles_deg]
            c_idx = min(range(len(c_angles)), key=lambda i: abs(c_angles[i]))
            c_plane = float(c_angles[c_idx])
            profile = []
            for gi, g in enumerate(g_angles):
                cd = float(phot.candela[c_idx][gi]) if gi < len(phot.candela[c_idx]) else 0.0
                profile.append({"gamma_deg": float(g), "cd": cd})
            result["c_plane_deg"] = c_plane
            result["c0_profile"] = profile
        result["asset_id"] = asset.id
        result["asset_format"] = asset.format
        result["asset_path"] = str(apath)
        print(json.dumps({"ok": True, "error": None, "result": result}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "result": None}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        resolved_project.to_string_lossy().to_string(),
        asset_id.trim().to_string(),
    ])?;
    let ok = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let error = payload
        .get("error")
        .and_then(|x| x.as_str())
        .map(|x| x.to_string());
    let result = payload.get("result").cloned();
    Ok(PhotometryVerifyResponse { ok, error, result })
}

#[tauri::command]
fn get_photometry_polar_data(file_path: String, format: Option<String>) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_file = PathBuf::from(file_path.trim());
    if raw_file.as_os_str().is_empty() {
        return Err("Photometry file path is empty".to_string());
    }
    let resolved_file = resolve_repo_relative(&raw_file, &cwd)?;
    let script = r##"
import json
import math
import sys
from pathlib import Path

import numpy as np

from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.plotting.plots import _resolve_polar_plane_pairs


def _nearest_idx(values: np.ndarray, target: float) -> int:
    if values.size == 0:
        return 0
    diffs = np.abs(values - float(target))
    return int(np.argmin(diffs))


def _find_threshold_angle(gamma_deg: np.ndarray, candela: np.ndarray, frac: float) -> float:
    if gamma_deg.size == 0 or candela.size == 0:
        return 0.0
    peak_idx = int(np.argmax(candela))
    peak = float(candela[peak_idx])
    if peak <= 1e-12:
        return float(gamma_deg[-1]) if gamma_deg.size > 0 else 0.0
    target = peak * float(frac)
    for i in range(peak_idx, candela.size):
        if float(candela[i]) <= target:
            return float(gamma_deg[i])
    return float(gamma_deg[-1])


def _integral_gamma(gamma_deg: np.ndarray, candela: np.ndarray, gamma_max_deg: float | None = None) -> float:
    if gamma_deg.size < 2 or candela.size < 2:
        return 0.0
    g = np.asarray(gamma_deg, dtype=float)
    i = np.asarray(candela, dtype=float)
    if gamma_max_deg is not None:
        gmax = float(gamma_max_deg)
        if gmax <= g[0]:
            return 0.0
        if gmax < g[-1]:
            interp_i = float(np.interp(gmax, g, i))
            keep = g < gmax
            g = np.concatenate([g[keep], np.array([gmax], dtype=float)])
            i = np.concatenate([i[keep], np.array([interp_i], dtype=float)])
    gr = np.deg2rad(g)
    return float(np.trapezoid(i * np.sin(gr), gr))


def _flux_ratio(c_angles_deg: np.ndarray, gamma_deg: np.ndarray, candela_matrix: np.ndarray) -> tuple[float, float, float]:
    if c_angles_deg.size == 0 or gamma_deg.size < 2 or candela_matrix.size == 0:
        return 0.0, 0.0, 0.0
    c = np.asarray(c_angles_deg, dtype=float)
    rows = np.asarray(candela_matrix, dtype=float)
    row_total = np.array([_integral_gamma(gamma_deg, row, None) for row in rows], dtype=float)
    row_down = np.array([_integral_gamma(gamma_deg, row, 90.0) for row in rows], dtype=float)
    if c[-1] < 359.5:
        c_ext = np.concatenate([c, np.array([c[0] + 360.0], dtype=float)])
        total_ext = np.concatenate([row_total, np.array([row_total[0]], dtype=float)])
        down_ext = np.concatenate([row_down, np.array([row_down[0]], dtype=float)])
    else:
        c_ext = c
        total_ext = row_total
        down_ext = row_down
    cr = np.deg2rad(c_ext)
    total_flux = float(np.trapezoid(total_ext, cr))
    downward_flux = float(np.trapezoid(down_ext, cr))
    ratio = (downward_flux / total_flux) if abs(total_flux) > 1e-12 else 0.0
    return total_flux, downward_flux, ratio


path = Path(sys.argv[1]).expanduser().resolve()
fmt = (sys.argv[2] if len(sys.argv) > 2 else "").strip().upper()
raw = path.read_text(encoding="utf-8", errors="replace")
if not fmt:
    fmt = "IES" if path.suffix.lower() == ".ies" else ("LDT" if path.suffix.lower() == ".ldt" else "IES")

total_lumens = None
if fmt == "IES":
    parsed = parse_ies_text(raw, source_path=path)
    phot = photometry_from_parsed_ies(parsed)
    total_lumens = float(phot.luminous_flux_lm) if phot.luminous_flux_lm is not None else None
elif fmt == "LDT":
    parsed = parse_ldt_text(raw)
    phot = photometry_from_parsed_ldt(parsed)
    if parsed.header and parsed.header.lamp_sets:
        total_lumens = float(sum(float(ls.total_flux) for ls in parsed.header.lamp_sets))
    elif phot.luminous_flux_lm is not None:
        total_lumens = float(phot.luminous_flux_lm)
else:
    raise ValueError(f"Unsupported photometry format: {fmt}")

c_angles = np.asarray(phot.c_angles_deg, dtype=float)
gamma_deg = np.asarray(phot.gamma_angles_deg, dtype=float)
candela = np.asarray(phot.candela, dtype=float)
if candela.ndim != 2:
    raise ValueError("Invalid candela matrix shape")
if candela.shape[0] != c_angles.size or candela.shape[1] != gamma_deg.size:
    raise ValueError("Candela matrix dimensions do not match angle arrays")

plane_pairs = _resolve_polar_plane_pairs([float(v) for v in c_angles], horizontal_plane_deg=None)
if len(plane_pairs) == 0:
    plane_pairs = [(float(c_angles[0]), float((c_angles[0] + 180.0) % 360.0))]

palette = ["#2E86AB", "#E94F37", "#A23B72", "#F18F01"]
planes_out = []
for i, (ca, cb) in enumerate(plane_pairs[:2]):
    ia = _nearest_idx(c_angles, float(ca))
    ib = _nearest_idx(c_angles, float(cb))
    row_a = np.asarray(candela[ia], dtype=float)
    row_b = np.asarray(candela[ib], dtype=float)
    planes_out.append(
        {
            "label": f"C{float(c_angles[ia]):.0f}-C{float(c_angles[ib]):.0f}",
            "color": palette[i % len(palette)],
            "half_a": {"gamma_deg": [float(g) for g in gamma_deg.tolist()], "candela": [float(v) for v in row_a.tolist()]},
            "half_b": {"gamma_deg": [float(g) for g in gamma_deg.tolist()], "candela": [float(v) for v in row_b.tolist()]},
        }
    )

ic0 = _nearest_idx(c_angles, 0.0)
c0 = np.asarray(candela[ic0], dtype=float)
beam_angle = _find_threshold_angle(gamma_deg, c0, 0.5)
field_angle = _find_threshold_angle(gamma_deg, c0, 0.1)
_, _, dfr = _flux_ratio(c_angles, gamma_deg, candela)

payload = {
    "planes": planes_out,
    "max_candela": float(np.max(candela)) if candela.size else 0.0,
    "total_lumens": float(total_lumens) if total_lumens is not None else None,
    "beam_angle_deg": float(beam_angle),
    "field_angle_deg": float(field_angle),
    "downward_flux_ratio": float(dfr),
}
print(json.dumps(payload))
"##;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        resolved_file.to_string_lossy().to_string(),
        format.unwrap_or_default().trim().to_string(),
    ])?;
    Ok(payload)
}

#[tauri::command]
fn get_luminaire_beam_data(project_path: String) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let script = r##"
import json
import math
import sys
from pathlib import Path

import numpy as np

from luxera.project.io import load_project_schema
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt

WORKPLANE_Z = 0.8


def _nearest_idx(values: np.ndarray, target: float) -> int:
    if values.size == 0:
        return 0
    return int(np.argmin(np.abs(values - float(target))))


def _find_threshold_angle(gamma_deg: np.ndarray, candela: np.ndarray, frac: float) -> float:
    if gamma_deg.size == 0 or candela.size == 0:
        return 0.0
    peak_idx = int(np.argmax(candela))
    peak = float(candela[peak_idx])
    if peak <= 1e-12:
        return float(gamma_deg[-1]) if gamma_deg.size else 0.0
    target = peak * float(frac)
    for i in range(peak_idx, candela.size):
        if float(candela[i]) <= target:
            return float(gamma_deg[i])
    return float(gamma_deg[-1])


def _resolve_asset_path(project_file: Path, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (project_file.parent / p).resolve()


def _beam_from_asset(project_file: Path, asset) -> dict | None:
    apath_raw = getattr(asset, "path", None)
    if not apath_raw:
        return None
    apath = _resolve_asset_path(project_file, str(apath_raw))
    if not apath.exists():
        return None
    fmt = str(getattr(asset, "format", "") or "").strip().upper()
    if not fmt:
        fmt = "IES" if apath.suffix.lower() == ".ies" else ("LDT" if apath.suffix.lower() == ".ldt" else "")
    raw = apath.read_text(encoding="utf-8", errors="replace")
    if fmt == "IES":
        parsed = parse_ies_text(raw, source_path=apath)
        phot = photometry_from_parsed_ies(parsed)
    elif fmt == "LDT":
        parsed = parse_ldt_text(raw)
        phot = photometry_from_parsed_ldt(parsed)
    else:
        return None
    c_angles = np.asarray(phot.c_angles_deg, dtype=float)
    gamma = np.asarray(phot.gamma_angles_deg, dtype=float)
    candela = np.asarray(phot.candela, dtype=float)
    if c_angles.size == 0 or gamma.size == 0 or candela.ndim != 2:
        return None
    i0 = _nearest_idx(c_angles, 0.0)
    i90 = _nearest_idx(c_angles, 90.0)
    c0 = np.asarray(candela[i0], dtype=float)
    c90 = np.asarray(candela[i90], dtype=float)
    return {
        "beam_half_angle_c0": float(_find_threshold_angle(gamma, c0, 0.5)),
        "beam_half_angle_c90": float(_find_threshold_angle(gamma, c90, 0.5)),
        "field_half_angle_c0": float(_find_threshold_angle(gamma, c0, 0.1)),
        "field_half_angle_c90": float(_find_threshold_angle(gamma, c90, 0.1)),
    }


def _radius_from_height(z: float, half_angle_deg: float, workplane_z: float = WORKPLANE_Z) -> float:
    mount_h = max(0.0, float(z) - float(workplane_z))
    angle = max(0.0, min(89.9, float(half_angle_deg)))
    return float(mount_h * math.tan(math.radians(angle)))


project_file = Path(sys.argv[1]).expanduser().resolve()
project = load_project_schema(project_file)

asset_beams: dict[str, dict] = {}
for asset in getattr(project, "photometry_assets", []):
    aid = str(getattr(asset, "id", "") or "").strip()
    if not aid:
        continue
    if aid in asset_beams:
        continue
    try:
        metrics = _beam_from_asset(project_file, asset)
    except Exception:
        metrics = None
    if metrics is not None:
        asset_beams[aid] = metrics

rows = []
for lum in getattr(project, "luminaires", []):
    lid = str(getattr(lum, "id", "") or "").strip()
    tr = getattr(lum, "transform", None)
    pos = getattr(tr, "position", (0.0, 0.0, 0.0)) if tr is not None else (0.0, 0.0, 0.0)
    rot = getattr(tr, "rotation", None) if tr is not None else None
    euler = getattr(rot, "euler_deg", None) if rot is not None else None
    x = float(pos[0]) if len(pos) > 0 else 0.0
    y = float(pos[1]) if len(pos) > 1 else 0.0
    z = float(pos[2]) if len(pos) > 2 else 0.0
    yaw = float(euler[0]) if (euler is not None and len(euler) > 0 and euler[0] is not None) else 0.0
    asset_id = str(getattr(lum, "photometry_asset_id", "") or "").strip()
    metrics = asset_beams.get(
        asset_id,
        {
            "beam_half_angle_c0": 0.0,
            "beam_half_angle_c90": 0.0,
            "field_half_angle_c0": 0.0,
            "field_half_angle_c90": 0.0,
        },
    )
    rows.append(
        {
            "id": lid,
            "x": x,
            "y": y,
            "z": z,
            "yaw_deg": yaw,
            "photometry_asset_id": asset_id,
            "beam_radius_c0": _radius_from_height(z, metrics["beam_half_angle_c0"]),
            "beam_radius_c90": _radius_from_height(z, metrics["beam_half_angle_c90"]),
            "field_radius_c0": _radius_from_height(z, metrics["field_half_angle_c0"]),
            "field_radius_c90": _radius_from_height(z, metrics["field_half_angle_c90"]),
            "beam_half_angle_c0": float(metrics["beam_half_angle_c0"]),
            "beam_half_angle_c90": float(metrics["beam_half_angle_c90"]),
            "field_half_angle_c0": float(metrics["field_half_angle_c0"]),
            "field_half_angle_c90": float(metrics["field_half_angle_c90"]),
        }
    )

print(json.dumps({"luminaires": rows}))
"##;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        resolved_project.to_string_lossy().to_string(),
    ])?;
    Ok(payload)
}

#[tauri::command]
fn add_luminaire_to_project(
    project_path: String,
    asset_id: String,
    luminaire_id: Option<String>,
    name: Option<String>,
    x: f64,
    y: f64,
    z: f64,
    yaw: Option<f64>,
    pitch: Option<f64>,
    roll: Option<f64>,
    maintenance: Option<f64>,
    multiplier: Option<f64>,
    tilt: Option<f64>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    if asset_id.trim().is_empty() {
        return Err("Photometry asset id is required".to_string());
    }
    let mut args = vec![
        "add-luminaire".to_string(),
        resolved_project.to_string_lossy().to_string(),
        "--asset".to_string(),
        asset_id.trim().to_string(),
        "--x".to_string(),
        x.to_string(),
        "--y".to_string(),
        y.to_string(),
        "--z".to_string(),
        z.to_string(),
        "--yaw".to_string(),
        yaw.unwrap_or(0.0).to_string(),
        "--pitch".to_string(),
        pitch.unwrap_or(0.0).to_string(),
        "--roll".to_string(),
        roll.unwrap_or(0.0).to_string(),
        "--maintenance".to_string(),
        maintenance.unwrap_or(1.0).to_string(),
        "--multiplier".to_string(),
        multiplier.unwrap_or(1.0).to_string(),
        "--tilt".to_string(),
        tilt.unwrap_or(0.0).to_string(),
    ];
    if let Some(v) = luminaire_id {
        if !v.trim().is_empty() {
            args.push("--id".to_string());
            args.push(v.trim().to_string());
        }
    }
    if let Some(v) = name {
        if !v.trim().is_empty() {
            args.push("--name".to_string());
            args.push(v.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn add_grid_to_project(
    project_path: String,
    name: Option<String>,
    width: f64,
    height: f64,
    elevation: f64,
    nx: i64,
    ny: i64,
    origin_x: Option<f64>,
    origin_y: Option<f64>,
    origin_z: Option<f64>,
    room_id: Option<String>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    let mut args = vec![
        "add-grid".to_string(),
        resolved_project.to_string_lossy().to_string(),
        "--width".to_string(),
        width.to_string(),
        "--height".to_string(),
        height.to_string(),
        "--elevation".to_string(),
        elevation.to_string(),
        "--nx".to_string(),
        nx.to_string(),
        "--ny".to_string(),
        ny.to_string(),
        "--origin-x".to_string(),
        origin_x.unwrap_or(0.0).to_string(),
        "--origin-y".to_string(),
        origin_y.unwrap_or(0.0).to_string(),
        "--origin-z".to_string(),
        origin_z.unwrap_or(0.0).to_string(),
    ];
    if let Some(v) = name {
        if !v.trim().is_empty() {
            args.push("--name".to_string());
            args.push(v.trim().to_string());
        }
    }
    if let Some(v) = room_id {
        if !v.trim().is_empty() {
            args.push("--room-id".to_string());
            args.push(v.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn add_job_to_project(
    project_path: String,
    job_id: Option<String>,
    job_type: String,
    backend: Option<String>,
    seed: Option<i64>,
) -> Result<GeometryOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    if job_type.trim().is_empty() {
        return Err("Job type is required".to_string());
    }
    let mut args = vec![
        "add-job".to_string(),
        resolved_project.to_string_lossy().to_string(),
        "--type".to_string(),
        job_type.trim().to_string(),
        "--backend".to_string(),
        backend.unwrap_or_else(|| "cpu".to_string()),
        "--seed".to_string(),
        seed.unwrap_or(0).to_string(),
    ];
    if let Some(v) = job_id {
        if !v.trim().is_empty() {
            args.push("--id".to_string());
            args.push(v.trim().to_string());
        }
    }
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    let project = if success {
        Some(open_project_file(resolved_project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(GeometryOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        project,
    })
}

#[tauri::command]
fn list_standard_profiles() -> Result<Value, String> {
    let script = r#"
import json
from typing import Dict, Any

from luxera.compliance import standards as std

requirements = getattr(std, "STANDARD_REQUIREMENTS", None)
if requirements is None:
    requirements = getattr(std, "EN_12464_1_REQUIREMENTS", {})
if requirements is None:
    requirements = {}

category_map = {
    "OFFICE_GENERAL": "Offices",
    "OFFICE_WRITING": "Offices",
    "OFFICE_TECHNICAL": "Offices",
    "OFFICE_CAD": "Offices",
    "CONFERENCE_ROOM": "Offices",
    "RECEPTION": "Offices",
    "WAREHOUSE_GENERAL": "Industrial",
    "WAREHOUSE_LOADING": "Industrial",
    "MANUFACTURING_ROUGH": "Industrial",
    "MANUFACTURING_MEDIUM": "Industrial",
    "MANUFACTURING_FINE": "Industrial",
    "MANUFACTURING_VERY_FINE": "Industrial",
    "RETAIL_GENERAL": "Retail",
    "RETAIL_SUPERMARKET": "Retail",
    "RETAIL_CHECKOUT": "Retail",
    "CLASSROOM": "Education",
    "LECTURE_HALL": "Education",
    "LABORATORY": "Education",
    "LIBRARY_READING": "Education",
    "LIBRARY_SHELVES": "Education",
    "HOSPITAL_CORRIDOR": "Healthcare",
    "HOSPITAL_WARD": "Healthcare",
    "HOSPITAL_EXAMINATION": "Healthcare",
    "HOSPITAL_OPERATING": "Healthcare",
    "CORRIDOR": "Circulation",
    "STAIRWAY": "Circulation",
    "LIFT_LOBBY": "Circulation",
    "ENTRANCE_HALL": "Circulation",
    "CANTEEN": "Amenity",
    "KITCHEN": "Amenity",
    "TOILET": "Amenity",
    "CHANGING_ROOM": "Amenity",
    "PARKING_GARAGE": "Parking",
}

def _activity_key(at: Any) -> str:
    if hasattr(at, "name"):
        return str(at.name)
    return str(at)

rows = []
for at, req in requirements.items():
    key = _activity_key(at).strip()
    if not key:
        continue
    rows.append({
        "activity_type": key,
        "description": str(getattr(req, "description", key)),
        "maintained_illuminance_lux": float(getattr(req, "maintained_illuminance", 0.0) or 0.0),
        "uniformity_min": float(getattr(req, "uniformity_min", 0.0) or 0.0),
        "ugr_max": float(getattr(req, "ugr_max", 0.0) or 0.0),
        "cri_min": int(getattr(req, "cri_min", 0) or 0),
        "standard_ref": str(getattr(req, "standard_reference", "EN 12464-1:2021")),
        "category": category_map.get(key, "Other"),
    })

rows.sort(key=lambda r: (str(r.get("category", "")), str(r.get("activity_type", ""))))
print(json.dumps(rows))
"#;
    let payload = run_python_json(&["-c".to_string(), script.to_string()])?;
    Ok(payload)
}

#[tauri::command]
fn set_compliance_profile_in_project(
    project_path: String,
    profile_id: String,
    activity_type: String,
    thresholds_json: String,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if profile_id.trim().is_empty() {
        return Err("Profile id is required".to_string());
    }
    if activity_type.trim().is_empty() {
        return Err("Activity type is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path

from luxera.compliance import standards as std
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import ComplianceProfile

project_path = Path(sys.argv[1]).expanduser().resolve()
profile_id = sys.argv[2].strip()
activity_type = sys.argv[3].strip()
raw_thresholds = sys.argv[4] if len(sys.argv) > 4 else "{}"

project = load_project_schema(project_path)

requirements = getattr(std, "STANDARD_REQUIREMENTS", None)
if requirements is None:
    requirements = getattr(std, "EN_12464_1_REQUIREMENTS", {})
if requirements is None:
    requirements = {}

req = None
for at, candidate in requirements.items():
    name = getattr(at, "name", str(at))
    if str(name).strip().upper() == activity_type.upper():
        req = candidate
        break
if req is None:
    raise ValueError(f"Unknown activity type: {activity_type}")

thresholds = {
    "maintained_illuminance_lux": float(getattr(req, "maintained_illuminance", 0.0) or 0.0),
    "uniformity_min": float(getattr(req, "uniformity_min", 0.0) or 0.0),
    "ugr_max": float(getattr(req, "ugr_max", 0.0) or 0.0),
    "cri_min": float(getattr(req, "cri_min", 0.0) or 0.0),
}
if raw_thresholds.strip():
    parsed = json.loads(raw_thresholds)
    if not isinstance(parsed, dict):
        raise ValueError("thresholds_json must be a JSON object")
    for k, v in parsed.items():
        try:
            thresholds[str(k)] = float(v)
        except Exception:
            continue

description = str(getattr(req, "description", activity_type))
profile = ComplianceProfile(
    id=profile_id,
    name=description,
    domain="indoor",
    standard_ref=str(getattr(req, "standard_reference", "EN 12464-1:2021")),
    thresholds=thresholds,
    notes=f"ActivityType={activity_type}",
)

updated = False
for i, existing in enumerate(project.compliance_profiles):
    if str(getattr(existing, "id", "")) == profile_id:
        project.compliance_profiles[i] = profile
        updated = True
        break
if not updated:
    project.compliance_profiles.append(profile)

save_project_schema(project, project_path)
print(json.dumps({
    "ok": True,
    "message": f"Applied compliance profile '{profile_id}' ({activity_type})",
    "data": {
        "profile_id": profile_id,
        "activity_type": activity_type,
        "thresholds": thresholds,
    },
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        profile_id.trim().to_string(),
        activity_type.trim().to_string(),
        thresholds_json,
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Compliance profile operation completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn evaluate_compliance_detailed(result_dir: String, project_path: String) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let result_path = resolve_repo_relative(&PathBuf::from(result_dir.trim()), &cwd)?;
    if !result_path.exists() || !result_path.is_dir() {
        return Err(format!("Result directory not found: {}", result_path.display()));
    }
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }

    let script = r#"
import json, sys
from pathlib import Path

from luxera.project.io import load_project_schema

result_dir = Path(sys.argv[1]).expanduser().resolve()
project_path = Path(sys.argv[2]).expanduser().resolve()

result_file = result_dir / "result.json"
if not result_file.exists():
    raise FileNotFoundError(f"Missing result.json in {result_dir}")

with result_file.open("r", encoding="utf-8") as f:
    result_payload = json.load(f)

summary = result_payload.get("summary") if isinstance(result_payload, dict) else {}
if not isinstance(summary, dict):
    summary = {}

def _as_float(value):
    if isinstance(value, (int, float)):
        v = float(value)
        if v == v and v not in (float("inf"), float("-inf")):
            return v
    return None

def _pick_first_numeric(src, keys):
    for key in keys:
        if not isinstance(src, dict):
            continue
        v = _as_float(src.get(key))
        if v is not None:
            return v
    return None

def _threshold(profile_thresholds, keys):
    if not isinstance(profile_thresholds, dict):
        return None
    for key in keys:
        v = _as_float(profile_thresholds.get(key))
        if v is not None:
            return v
    return None

def _metric_check(metric, actual, required, unit, direction):
    if required is None:
        return {
            "metric": metric,
            "actual": actual,
            "required": None,
            "unit": unit,
            "direction": direction,
            "status": "N/A",
            "delta": None,
            "delta_percent": None,
            "suggestion": None,
        }
    if actual is None:
        return {
            "metric": metric,
            "actual": None,
            "required": required,
            "unit": unit,
            "direction": direction,
            "status": "N/A",
            "delta": None,
            "delta_percent": None,
            "suggestion": None,
        }
    delta = actual - required
    delta_percent = (delta / required * 100.0) if abs(required) > 1e-12 else None
    passed = actual >= required if direction == ">=" else actual <= required
    status = "PASS" if passed else "FAIL"
    suggestion = None
    if status == "FAIL":
        if metric.startswith("Maintained Illuminance"):
            suggestion = f"Increase by ~{abs(delta):.0f} lux. Try: reduce luminaire spacing, increase flux multiplier, or add luminaires."
        elif metric.startswith("Uniformity"):
            suggestion = f"Improve uniformity by {abs(delta):.2f}. Try: reduce spacing between luminaires or add supplementary luminaires in dark areas."
        elif metric.startswith("Glare Rating"):
            suggestion = f"Reduce glare by {abs(delta):.1f} points. Try: increase mounting height, use lower-luminance luminaires, or adjust aiming."
        elif metric.startswith("Minimum Illuminance"):
            suggestion = f"Increase minimum illuminance by ~{abs(delta):.0f} lux. Try: fill dark zones with additional luminaires and tighten spacing."
    return {
        "metric": metric,
        "actual": actual,
        "required": required,
        "unit": unit,
        "direction": direction,
        "status": status,
        "delta": delta,
        "delta_percent": delta_percent,
        "suggestion": suggestion,
    }

project = load_project_schema(project_path)
profiles = list(getattr(project, "compliance_profiles", []) or [])
if not profiles:
    print(json.dumps({
        "profile_name": None,
        "standard": None,
        "overall_status": "NO_PROFILE",
        "checks": [],
    }))
    raise SystemExit(0)

profile = profiles[0]
thresholds = dict(getattr(profile, "thresholds", {}) or {})

mean_lux = _pick_first_numeric(summary, ("mean_lux", "avg_lux", "mean_illuminance_lux"))
min_lux = _pick_first_numeric(summary, ("min_lux", "minimum_lux", "emin_lux"))
uniformity_ratio = _pick_first_numeric(summary, ("uniformity_ratio", "u0", "uniformity"))
ugr_worst_case = _pick_first_numeric(summary, ("ugr_worst_case", "highest_ugr", "ugr"))

checks = [
    _metric_check(
        "Maintained Illuminance (Em)",
        mean_lux,
        _threshold(thresholds, ("maintained_illuminance_lux", "target_lux", "em_lux")),
        "lux",
        ">=",
    ),
    _metric_check(
        "Minimum Illuminance (Emin)",
        min_lux,
        _threshold(thresholds, ("minimum_illuminance_lux", "emin_lux")),
        "lux",
        ">=",
    ),
    _metric_check(
        "Uniformity (Uo)",
        uniformity_ratio,
        _threshold(thresholds, ("uniformity_min", "u0_min")),
        "",
        ">=",
    ),
    _metric_check(
        "Glare Rating (UGR)",
        ugr_worst_case,
        _threshold(thresholds, ("ugr_max", "ugr_limit")),
        "",
        "<=",
    ),
]
checks = [c for c in checks if c.get("required") is not None or c.get("actual") is not None]

overall_status = "PASS"
for c in checks:
    if c.get("status") == "FAIL":
        overall_status = "FAIL"
        break
if checks and all(c.get("status") == "N/A" for c in checks):
    overall_status = "N/A"

print(json.dumps({
    "profile_name": str(getattr(profile, "id", "") or getattr(profile, "name", "") or "Compliance Profile"),
    "standard": str(getattr(profile, "standard_ref", "") or "EN 12464-1:2021"),
    "overall_status": overall_status,
    "checks": checks,
}))
"#;
    run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        result_path.to_string_lossy().to_string(),
        project.to_string_lossy().to_string(),
    ])
}

#[tauri::command]
fn estimate_illuminance_fast(project_path: String) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    let script = r#"
import json, math, os, sys
from pathlib import Path

from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.io import load_project_schema

def _as_float(v, default=0.0):
    try:
        x = float(v)
        if x == x and x not in (float("inf"), float("-inf")):
            return x
    except Exception:
        pass
    return default

def approx_uf(ri: float, rho_c: float, rho_w: float, rho_f: float) -> float:
    base = 0.25 + 0.15 * min(max(ri, 0.0), 5.0)
    ceiling_boost = max(0.0, min(1.0, rho_c)) * 0.15
    wall_boost = max(0.0, min(1.0, rho_w)) * 0.10
    floor_effect = max(0.0, min(1.0, rho_f)) * 0.02
    return min(0.85, max(0.05, base + ceiling_boost + wall_boost + floor_effect))

def _load_asset_flux_lm(project_dir: Path, asset) -> float | None:
    path = getattr(asset, "path", None)
    fmt = str(getattr(asset, "format", "") or "").strip().upper()
    if not path:
        return None
    ap = Path(path).expanduser()
    if not ap.is_absolute():
        ap = (project_dir / ap).resolve()
    if not ap.exists() or not ap.is_file():
        return None
    text = ap.read_text(encoding="utf-8", errors="replace")
    if fmt == "IES":
        parsed = parse_ies_text(text, source_path=ap)
        phot = photometry_from_parsed_ies(parsed)
        flux = getattr(phot, "luminous_flux_lm", None)
        return float(flux) if isinstance(flux, (int, float)) and float(flux) > 0 else None
    if fmt == "LDT":
        parsed = parse_ldt_text(text)
        phot = photometry_from_parsed_ldt(parsed)
        flux = getattr(phot, "luminous_flux_lm", None)
        if isinstance(flux, (int, float)) and float(flux) > 0:
            return float(flux)
        lamp_sets = getattr(parsed.header, "lamp_sets", []) or []
        total = 0.0
        for ls in lamp_sets:
            total += max(0.0, _as_float(getattr(ls, "total_flux", 0.0), 0.0))
        return total if total > 0 else None
    return None

project_path = Path(sys.argv[1]).expanduser().resolve()
project = load_project_schema(project_path)
project_dir = project_path.parent

rooms = list(getattr(project, "geometry", None).rooms if getattr(project, "geometry", None) is not None else [])
luminaires = list(getattr(project, "luminaires", []) or [])
assets = list(getattr(project, "photometry_assets", []) or [])
asset_by_id = {str(getattr(a, "id", "") or ""): a for a in assets}

if not rooms or not luminaires:
    print(json.dumps({
        "estimated_mean_lux": None,
        "estimated_uniformity": None,
        "luminaire_count": len(luminaires),
        "total_lumens": 0.0,
        "room_area_m2": None,
        "room_index": None,
        "utilization_factor": None,
        "avg_maintenance_factor": None,
        "confidence": "low",
    }))
    raise SystemExit(0)

room = rooms[0]
room_w = max(0.0, _as_float(getattr(room, "width", 0.0), 0.0))
room_l = max(0.0, _as_float(getattr(room, "length", 0.0), 0.0))
if room_w <= 0.0 or room_l <= 0.0:
    print(json.dumps({
        "estimated_mean_lux": None,
        "estimated_uniformity": None,
        "luminaire_count": len(luminaires),
        "total_lumens": 0.0,
        "room_area_m2": None,
        "room_index": None,
        "utilization_factor": None,
        "avg_maintenance_factor": None,
        "confidence": "low",
    }))
    raise SystemExit(0)

rho_f = max(0.0, min(1.0, _as_float(getattr(room, "floor_reflectance", 0.2), 0.2)))
rho_w = max(0.0, min(1.0, _as_float(getattr(room, "wall_reflectance", 0.5), 0.5)))
rho_c = max(0.0, min(1.0, _as_float(getattr(room, "ceiling_reflectance", 0.7), 0.7)))

asset_flux_cache: dict[str, float | None] = {}
workplane_z = 0.8
mount_heights: list[float] = []
maintenance_vals: list[float] = []
effective_flux_per_lum: list[float] = []
known_flux_count = 0

for lum in luminaires:
    aid = str(getattr(lum, "photometry_asset_id", "") or "")
    if aid not in asset_flux_cache:
        asset = asset_by_id.get(aid)
        asset_flux_cache[aid] = _load_asset_flux_lm(project_dir, asset) if asset is not None else None
    base_flux = asset_flux_cache.get(aid)
    mult = max(0.0, _as_float(getattr(lum, "flux_multiplier", 1.0), 1.0))
    mf = max(0.0, _as_float(getattr(lum, "maintenance_factor", 1.0), 1.0))
    maintenance_vals.append(mf)
    transform = getattr(lum, "transform", None)
    pos = getattr(transform, "position", None) if transform is not None else None
    z = _as_float(pos[2], 2.8) if isinstance(pos, (list, tuple)) and len(pos) >= 3 else 2.8
    mount_heights.append(max(0.1, z - workplane_z))
    if isinstance(base_flux, (int, float)) and float(base_flux) > 0:
        known_flux_count += 1
        effective_flux_per_lum.append(float(base_flux) * mult)
    else:
        effective_flux_per_lum.append(0.0)

luminaire_count = len(luminaires)
area = room_w * room_l
hm = sum(mount_heights) / max(1, len(mount_heights))
ri = (room_w * room_l) / max(1e-6, hm * (room_w + room_l))
uf = approx_uf(ri, rho_c, rho_w, rho_f)
avg_mf = sum(maintenance_vals) / max(1, len(maintenance_vals))
total_lumens = float(sum(effective_flux_per_lum))
phi_avg = (total_lumens / luminaire_count) if luminaire_count > 0 else 0.0
estimated_em = (luminaire_count * phi_avg * uf * avg_mf) / area if area > 1e-9 else None
u0 = 0.4 + 0.3 * min(max(ri, 0.0), 3.0) / 3.0
u0 = max(0.0, min(1.0, u0))

coverage = known_flux_count / max(1, luminaire_count)
confidence = "high" if coverage >= 0.8 else ("medium" if coverage >= 0.5 else "low")
if luminaire_count < 2:
    confidence = "low"

print(json.dumps({
    "estimated_mean_lux": float(estimated_em) if estimated_em is not None else None,
    "estimated_uniformity": float(u0),
    "luminaire_count": luminaire_count,
    "total_lumens": float(total_lumens),
    "room_area_m2": float(area),
    "room_index": float(ri),
    "utilization_factor": float(uf),
    "avg_maintenance_factor": float(avg_mf),
    "confidence": confidence,
}))
"#;
    run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
    ])
}

#[tauri::command]
fn propose_quick_layout(
    project_path: String,
    target_lux: f64,
    max_rows: Option<i32>,
    max_cols: Option<i32>,
) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if !target_lux.is_finite() || target_lux <= 0.0 {
        return Err("Target illuminance must be a positive number".to_string());
    }
    let max_rows_v = max_rows.unwrap_or(6).max(1);
    let max_cols_v = max_cols.unwrap_or(6).max(1);
    let script = r#"
import json, os, sys
from pathlib import Path

from luxera.optim.layout import propose_layout
from luxera.project.io import load_project_schema

project_path = Path(sys.argv[1]).expanduser().resolve()
target_lux = float(sys.argv[2])
max_rows = int(sys.argv[3])
max_cols = int(sys.argv[4])

project = load_project_schema(project_path)
os.chdir(project_path.parent)
lums, best = propose_layout(project, target_lux=target_lux, max_rows=max_rows, max_cols=max_cols)

rows = []
for idx, lum in enumerate(lums, start=1):
    pos = lum.transform.position
    rows.append({
        "id": f"ql_{idx}",
        "name": str(getattr(lum, "name", "Luminaire")),
        "x": float(pos[0]),
        "y": float(pos[1]),
        "z": float(pos[2]),
        "asset_id": str(lum.photometry_asset_id),
        "yaw_deg": float((lum.transform.rotation.euler_deg or (0.0, 0.0, 0.0))[0]),
        "maintenance_factor": float(getattr(lum, "maintenance_factor", 1.0)),
        "flux_multiplier": float(getattr(lum, "flux_multiplier", 1.0)),
    })

print(json.dumps({
    "best": {
        "rows": int(best.rows),
        "cols": int(best.cols),
        "mean_lux": float(best.mean_lux),
        "uniformity": float(best.uniformity),
        "fixture_count": len(rows),
    },
    "luminaires": rows,
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        target_lux.to_string(),
        max_rows_v.to_string(),
        max_cols_v.to_string(),
    ])?;
    Ok(payload)
}

#[tauri::command]
fn apply_quick_layout(project_path: String, luminaires_json: String) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    let script = r#"
import json, sys
from pathlib import Path

from luxera.project.history import push_snapshot
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import LuminaireInstance, RotationSpec, TransformSpec

project_path = Path(sys.argv[1]).expanduser().resolve()
raw = sys.argv[2] if len(sys.argv) > 2 else "[]"
items = json.loads(raw)
if not isinstance(items, list):
    raise ValueError("luminaires_json must be a JSON array")

project = load_project_schema(project_path)
push_snapshot(project, label="quick_layout_apply")

new_lums = []
for i, row in enumerate(items, start=1):
    if not isinstance(row, dict):
        continue
    lid = str(row.get("id") or f"ql_{i}")
    name = str(row.get("name") or f"Quick Layout {i}")
    asset_id = str(row.get("asset_id") or "").strip()
    if not asset_id:
        raise ValueError(f"Missing asset_id for luminaire {lid}")
    x = float(row.get("x", 0.0))
    y = float(row.get("y", 0.0))
    z = float(row.get("z", 0.0))
    yaw = float(row.get("yaw_deg", 0.0))
    mf = float(row.get("maintenance_factor", 1.0))
    mult = float(row.get("flux_multiplier", 1.0))
    new_lums.append(
        LuminaireInstance(
            id=lid,
            name=name,
            photometry_asset_id=asset_id,
            transform=TransformSpec(
                position=(x, y, z),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(yaw, 0.0, 0.0)),
            ),
            maintenance_factor=mf,
            flux_multiplier=mult,
        )
    )

project.luminaires = new_lums
save_project_schema(project, project_path)
print(json.dumps({
    "ok": True,
    "message": f"Applied quick layout with {len(new_lums)} luminaires",
    "data": {"count": len(new_lums)},
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        luminaires_json,
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Quick layout apply completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn export_debug_bundle(project_path: String, job_id: String, output_path: String) -> Result<ExportOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    let out = resolve_repo_relative(&PathBuf::from(output_path.trim()), &cwd)?;
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }
    let args = vec![
        "export-debug".to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        "--out".to_string(),
        out.to_string_lossy().to_string(),
    ];
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    Ok(ExportOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        output_path: out.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn export_client_bundle(project_path: String, job_id: String, output_path: String) -> Result<ExportOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    let out = resolve_repo_relative(&PathBuf::from(output_path.trim()), &cwd)?;
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }
    let args = vec![
        "export-client".to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        "--out".to_string(),
        out.to_string_lossy().to_string(),
    ];
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    Ok(ExportOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        output_path: out.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn export_backend_compare(project_path: String, job_id: String, output_path: String) -> Result<ExportOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    let out = resolve_repo_relative(&PathBuf::from(output_path.trim()), &cwd)?;
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }
    let args = vec![
        "export-backend-compare".to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        "--out".to_string(),
        out.to_string_lossy().to_string(),
    ];
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    Ok(ExportOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        output_path: out.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn export_roadway_report(project_path: String, job_id: String, output_path: String) -> Result<ExportOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    let out = resolve_repo_relative(&PathBuf::from(output_path.trim()), &cwd)?;
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Cannot create {}: {}", parent.display(), e))?;
    }
    let args = vec![
        "export-roadway-report".to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        "--out".to_string(),
        out.to_string_lossy().to_string(),
    ];
    let (success, exit_code, stdout, stderr) = run_luxera_cli(&args)?;
    Ok(ExportOperationResult {
        success,
        exit_code,
        stdout,
        stderr,
        output_path: out.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn execute_agent_intent(project_path: String, intent: String, approvals_json: Option<String>) -> Result<AgentRuntimeResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if intent.trim().is_empty() {
        return Err("Intent is empty".to_string());
    }
    let script = r#"
import json, sys
from luxera.agent.runtime import AgentRuntime
project_path = sys.argv[1]
intent = sys.argv[2]
approvals = {}
if len(sys.argv) > 3 and sys.argv[3].strip():
    approvals = json.loads(sys.argv[3])
rt = AgentRuntime()
res = rt.execute(project_path=project_path, intent=intent, approvals=approvals)
print(json.dumps(res.to_dict()))
"#;
    let args = vec![
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        intent,
        approvals_json.unwrap_or_else(|| "{}".to_string()),
    ];
    let payload = run_python_json(&args)?;
    Ok(AgentRuntimeResult { response: payload })
}

#[tauri::command]
fn execute_agent_turn(
    project_path: String,
    intent: String,
    conversation_json: Option<String>,
    approvals_json: Option<String>,
) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if intent.trim().is_empty() {
        return Err("Intent is empty".to_string());
    }
    let script = r#"
import json, sys
from luxera.agent.runtime import AgentRuntime

project_path = sys.argv[1]
intent = sys.argv[2]
conversation_raw = sys.argv[3] if len(sys.argv) > 3 else "[]"
approvals_raw = sys.argv[4] if len(sys.argv) > 4 else "{}"

conversation = []
try:
    parsed = json.loads(conversation_raw) if conversation_raw.strip() else []
    if isinstance(parsed, list):
        conversation = parsed
except Exception:
    conversation = []

approvals = {}
if approvals_raw.strip():
    try:
        parsed_approvals = json.loads(approvals_raw)
        if isinstance(parsed_approvals, dict):
            approvals = parsed_approvals
    except Exception:
        approvals = {}

context_parts = []
for turn in conversation:
    if not isinstance(turn, dict):
        continue
    role = str(turn.get("role", "")).strip().lower()
    content = str(turn.get("content", "")).strip()
    if role == "user":
        if content:
            context_parts.append(f"User said: {content}")
    else:
        summary = str(turn.get("summary", "")).strip()
        if summary:
            context_parts.append(f"Assistant did: {summary}")
        elif content:
            context_parts.append(f"Assistant did: {content}")

context_str = "\n".join(context_parts[-6:])
if context_str:
    augmented_intent = f"Context:\n{context_str}\n\nCurrent request: {intent}"
else:
    augmented_intent = intent

rt = AgentRuntime()
res = rt.execute(project_path=project_path, intent=augmented_intent, approvals=approvals)
res_dict = res.to_dict()
actions = res_dict.get("actions", []) if isinstance(res_dict, dict) else []
warnings = res_dict.get("warnings", []) if isinstance(res_dict, dict) else []
produced = res_dict.get("produced_artifacts", []) if isinstance(res_dict, dict) else []
summary = (
    f"Executed {len(actions) if isinstance(actions, list) else 0} action(s)"
    f"; warnings={len(warnings) if isinstance(warnings, list) else 0}"
    f"; artifacts={len([x for x in produced if x]) if isinstance(produced, list) else 0}."
)
print(json.dumps({
    "response": res_dict,
    "summary": summary,
    "augmented_intent": augmented_intent,
}))
"#;
    let args = vec![
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        intent,
        conversation_json.unwrap_or_else(|| "[]".to_string()),
        approvals_json.unwrap_or_else(|| "{}".to_string()),
    ];
    run_python_json(&args)
}

#[tauri::command]
fn assign_material_in_project(
    project_path: String,
    material_id: String,
    surface_ids_csv: String,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if material_id.trim().is_empty() {
        return Err("Material id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
material_id = sys.argv[2].strip()
surface_ids = [x.strip() for x in sys.argv[3].split(",") if x.strip()]
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.assign_material(project, material_id=material_id, surface_ids=surface_ids, approved=True)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        material_id.trim().to_string(),
        surface_ids_csv,
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Material assignment completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn add_project_variant(
    project_path: String,
    variant_id: String,
    name: String,
    description: Option<String>,
    diff_ops_json: Option<String>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if variant_id.trim().is_empty() {
        return Err("Variant id is required".to_string());
    }
    if name.trim().is_empty() {
        return Err("Variant name is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
variant_id = sys.argv[2].strip()
name = sys.argv[3].strip()
description = sys.argv[4] if len(sys.argv) > 4 else ""
raw_ops = sys.argv[5] if len(sys.argv) > 5 else ""
diff_ops = []
if raw_ops.strip():
    parsed = json.loads(raw_ops)
    if not isinstance(parsed, list):
        raise ValueError("diff_ops_json must be a JSON array")
    diff_ops = parsed
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.add_variant(project, variant_id=variant_id, name=name, description=description, diff_ops=diff_ops)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        variant_id.trim().to_string(),
        name.trim().to_string(),
        description.unwrap_or_default(),
        diff_ops_json.unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Variant operation completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn compare_project_variants(
    project_path: String,
    job_id: String,
    variant_ids_csv: String,
    baseline_variant_id: Option<String>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if job_id.trim().is_empty() {
        return Err("Job id is required".to_string());
    }
    if variant_ids_csv.trim().is_empty() {
        return Err("At least one variant id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
project_path = str(Path(sys.argv[1]).expanduser().resolve())
job_id = sys.argv[2].strip()
variant_ids = [x.strip() for x in sys.argv[3].split(",") if x.strip()]
baseline = sys.argv[4].strip() if len(sys.argv) > 4 else ""
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.compare_variants(project, job_id=job_id, variant_ids=variant_ids, baseline_variant_id=(baseline or None))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        variant_ids_csv,
        baseline_variant_id.unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Variant compare completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: None,
    })
}

#[tauri::command]
fn compare_variants_visual(
    project_path: String,
    job_id: String,
    variant_ids_csv: String,
) -> Result<Value, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if job_id.trim().is_empty() {
        return Err("Job id is required".to_string());
    }
    if variant_ids_csv.trim().is_empty() {
        return Err("At least one variant id is required".to_string());
    }
    let script = r#"
import base64
import csv
import io
import json
import re
import tempfile
from pathlib import Path

import numpy as np

from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory
from luxera.project.variants import _apply_variant
from luxera.results.grid_viz import write_grid_heatmap_and_isolux


def _to_float(v, default=None):
    try:
        out = float(v)
        if np.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(text).strip())
    return clean.strip("_") or "grid"


def _first_threshold(project):
    profiles = list(getattr(project, "compliance_profiles", []) or [])
    if not profiles:
        return {"mean_lux_min": None, "uniformity_min": None, "ugr_max": None}
    thresholds = getattr(profiles[0], "thresholds", {}) or {}
    return {
        "mean_lux_min": _to_float(thresholds.get("maintained_illuminance_lux", thresholds.get("target_lux"))),
        "uniformity_min": _to_float(thresholds.get("uniformity_min")),
        "ugr_max": _to_float(thresholds.get("ugr_max")),
    }


def _candidate_csvs(result_dir: Path, grid_row: dict):
    out = []
    gid = str(grid_row.get("id", "")).strip()
    gname = str(grid_row.get("name", "")).strip()
    if gid:
        out.append(result_dir / f"grid_{gid}.csv")
    if gname:
        out.append(result_dir / f"grid_{_slug(gname)}.csv")
    out.append(result_dir / "grid.csv")
    seen = set()
    unique = []
    for p in out:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        unique.append(p)
    return unique


def _load_grid_points_values(result_dir: Path):
    tables_path = result_dir / "tables.json"
    if not tables_path.exists():
        return None
    tables = json.loads(tables_path.read_text(encoding="utf-8"))
    grids = (((tables or {}).get("tables") or {}).get("grids") or [])
    if not grids:
        return None
    row = grids[0] if isinstance(grids[0], dict) else {}
    nx = int(row.get("nx", 0) or 0)
    ny = int(row.get("ny", 0) or 0)
    if nx <= 0 or ny <= 0:
        return None
    for csv_path in _candidate_csvs(result_dir, row):
        if not csv_path.exists():
            continue
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                pts = []
                vals = []
                for rec in reader:
                    pts.append([float(rec["x"]), float(rec["y"]), float(rec.get("z", 0.0))])
                    vals.append(float(rec["lux"]))
            points = np.asarray(pts, dtype=float)
            values = np.asarray(vals, dtype=float)
            if points.shape[0] == nx * ny and values.shape[0] == nx * ny:
                return points, values, nx, ny
        except Exception:
            continue
    return None


def _to_heatmap_b64(result_dir: Path):
    loaded = _load_grid_points_values(result_dir)
    if loaded is None:
        return None
    points, values, nx, ny = loaded
    with tempfile.TemporaryDirectory(prefix="luxera_variant_heat_") as td:
        out = write_grid_heatmap_and_isolux(Path(td), points, values, nx, ny)
        heatmap_path = out.get("heatmap")
        if not heatmap_path or not Path(heatmap_path).exists():
            return None
        raw = Path(heatmap_path).read_bytes()
        return base64.b64encode(raw).decode("ascii")


def _summary_metric(summary: dict, *keys):
    for k in keys:
        if k in summary:
            v = _to_float(summary.get(k))
            if v is not None:
                return v
    return None


def _is_compliant(metrics: dict, thresholds: dict):
    checks = []
    if thresholds.get("mean_lux_min") is not None and metrics.get("mean_lux") is not None:
        checks.append(metrics["mean_lux"] >= thresholds["mean_lux_min"])
    if thresholds.get("uniformity_min") is not None and metrics.get("uniformity") is not None:
        checks.append(metrics["uniformity"] >= thresholds["uniformity_min"])
    if thresholds.get("ugr_max") is not None and metrics.get("ugr") is not None:
        checks.append(metrics["ugr"] <= thresholds["ugr_max"])
    return bool(checks) and all(checks)


project_path = str(Path(sys.argv[1]).expanduser().resolve())
job_id = sys.argv[2].strip()
variant_ids = [x.strip() for x in sys.argv[3].split(",") if x.strip()]

project = load_project_schema(project_path)
project.root_dir = str(Path(project_path).parent)
variant_by_id = {v.id: v for v in project.variants}
thresholds = _first_threshold(project)

variants_out = []
for vid in variant_ids:
    variant = variant_by_id.get(vid)
    if variant is None:
        variants_out.append(
            {
                "id": vid,
                "name": vid,
                "metrics": {"mean_lux": None, "uniformity": None, "ugr": None, "fixture_count": None},
                "heatmap_base64": None,
                "compliant": False,
                "error": f"Unknown variant id: {vid}",
            }
        )
        continue
    try:
        vp = _apply_variant(project, variant)
        ref = run_job_in_memory(vp, job_id)
        summary = dict(ref.summary or {})
        metrics = {
            "mean_lux": _summary_metric(summary, "mean_lux", "E_avg"),
            "uniformity": _summary_metric(summary, "uniformity_ratio", "uniformity_min_avg", "U0"),
            "ugr": _summary_metric(summary, "ugr_worst_case", "UGR"),
            "fixture_count": int(len(getattr(vp, "luminaires", []) or [])),
        }
        variants_out.append(
            {
                "id": variant.id,
                "name": variant.name,
                "metrics": metrics,
                "heatmap_base64": _to_heatmap_b64(Path(ref.result_dir)),
                "compliant": _is_compliant(metrics, thresholds),
                "error": None,
            }
        )
    except Exception as e:
        variants_out.append(
            {
                "id": variant.id,
                "name": variant.name,
                "metrics": {"mean_lux": None, "uniformity": None, "ugr": None, "fixture_count": None},
                "heatmap_base64": None,
                "compliant": False,
                "error": str(e),
            }
        )

ok_rows = [v for v in variants_out if not v.get("error")]

def _best_by(metric: str, mode: str):
    rows = [r for r in ok_rows if _to_float(((r.get("metrics") or {}).get(metric))) is not None]
    if not rows:
        return None
    if mode == "max":
        best = max(rows, key=lambda r: float(r["metrics"][metric]))
    else:
        best = min(rows, key=lambda r: float(r["metrics"][metric]))
    return best.get("id")

comparison = {
    "best_illuminance": _best_by("mean_lux", "max"),
    "best_uniformity": _best_by("uniformity", "max"),
    "best_efficiency": _best_by("fixture_count", "min"),
    "best_glare": _best_by("ugr", "min"),
}

print(
    json.dumps(
        {
            "variants": variants_out,
            "comparison": comparison,
            "thresholds": thresholds,
        }
    )
)
"#;
    run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        variant_ids_csv,
    ])
}

#[tauri::command]
fn propose_project_optimizations(
    project_path: String,
    job_id: String,
    constraints_json: Option<String>,
    top_n: Option<i64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if job_id.trim().is_empty() {
        return Err("Job id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
project_path = str(Path(sys.argv[1]).expanduser().resolve())
job_id = sys.argv[2].strip()
raw_constraints = sys.argv[3] if len(sys.argv) > 3 else ""
top_n = int(sys.argv[4]) if len(sys.argv) > 4 else 5
constraints = {}
if raw_constraints.strip():
    parsed = json.loads(raw_constraints)
    if not isinstance(parsed, dict):
        raise ValueError("constraints_json must be a JSON object")
    constraints = parsed
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.propose_optimizations(project, job_id=job_id, constraints=constraints, top_n=top_n)
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        job_id.trim().to_string(),
        constraints_json.unwrap_or_default(),
        top_n.unwrap_or(5).to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Optimization proposal completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: None,
    })
}

#[tauri::command]
fn apply_project_optimization_option(project_path: String, option_json: String) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if option_json.trim().is_empty() {
        return Err("Optimization option JSON is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
option = json.loads(sys.argv[2])
if not isinstance(option, dict):
    raise ValueError("option_json must be a JSON object")
tools = AgentTools()
project, _ = tools.open_project(project_path)
diff_res = tools.optimization_option_diff(project, option=option)
if not diff_res.ok:
    print(json.dumps({"ok": False, "message": diff_res.message, "data": {"preview": diff_res.data.get("preview", {}) if isinstance(diff_res.data, dict) else {}}}))
    raise SystemExit(0)
diff_obj = diff_res.data.get("diff")
apply_res = tools.apply_diff(project, diff=diff_obj, approved=True)
if apply_res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({
    "ok": apply_res.ok,
    "message": apply_res.message if apply_res.message else diff_res.message,
    "data": {
        "preview": diff_res.data.get("preview", {}) if isinstance(diff_res.data, dict) else {},
        "apply": apply_res.data if isinstance(apply_res.data, dict) else {},
    }
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        option_json,
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Optimization apply completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn edit_room_in_project(
    project_path: String,
    room_id: String,
    name: Option<String>,
    width: Option<f64>,
    length: Option<f64>,
    height: Option<f64>,
    origin_x: Option<f64>,
    origin_y: Option<f64>,
    origin_z: Option<f64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if room_id.trim().is_empty() {
        return Err("Room id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
room_id = sys.argv[2].strip()
raw_name, raw_w, raw_l, raw_h, raw_ox, raw_oy, raw_oz = sys.argv[3:10]
updates = {}
if raw_name.strip():
    updates["name"] = raw_name.strip()
if raw_w.strip():
    updates["width"] = float(raw_w)
if raw_l.strip():
    updates["length"] = float(raw_l)
if raw_h.strip():
    updates["height"] = float(raw_h)
if raw_ox.strip() or raw_oy.strip() or raw_oz.strip():
    updates["origin"] = (
        float(raw_ox) if raw_ox.strip() else 0.0,
        float(raw_oy) if raw_oy.strip() else 0.0,
        float(raw_oz) if raw_oz.strip() else 0.0,
    )
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.edit_room(project, room_id=room_id, updates=updates, approved=True)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        room_id.trim().to_string(),
        name.unwrap_or_default(),
        width.map(|v| v.to_string()).unwrap_or_default(),
        length.map(|v| v.to_string()).unwrap_or_default(),
        height.map(|v| v.to_string()).unwrap_or_default(),
        origin_x.map(|v| v.to_string()).unwrap_or_default(),
        origin_y.map(|v| v.to_string()).unwrap_or_default(),
        origin_z.map(|v| v.to_string()).unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Room edit completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn set_daylight_aperture_in_project(
    project_path: String,
    opening_id: String,
    visible_transmittance: Option<f64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if opening_id.trim().is_empty() {
        return Err("Opening id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
opening_id = sys.argv[2].strip()
vt_raw = sys.argv[3] if len(sys.argv) > 3 else ""
tools = AgentTools()
project, _ = tools.open_project(project_path)
vt = float(vt_raw) if vt_raw.strip() else None
res = tools.set_daylight_aperture(project, opening_id=opening_id, vt=vt)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        opening_id.trim().to_string(),
        visible_transmittance.map(|v| v.to_string()).unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Daylight aperture update completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn add_escape_route_in_project(
    project_path: String,
    route_id: String,
    polyline_csv: String,
    width_m: Option<f64>,
    spacing_m: Option<f64>,
    height_m: Option<f64>,
    end_margin_m: Option<f64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if route_id.trim().is_empty() {
        return Err("Route id is required".to_string());
    }
    if polyline_csv.trim().is_empty() {
        return Err("Route polyline is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
route_id = sys.argv[2].strip()
polyline_csv = sys.argv[3].strip()
width_m = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].strip() else 1.0
spacing_m = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].strip() else 0.5
height_m = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6].strip() else 0.0
end_margin_m = float(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7].strip() else 0.0
pts = []
for token in polyline_csv.split(";"):
    token = token.strip()
    if not token:
        continue
    parts = [p.strip() for p in token.split(",")]
    if len(parts) != 3:
        raise ValueError("Each polyline point must be 'x,y,z' and points separated by ';'")
    pts.append((float(parts[0]), float(parts[1]), float(parts[2])))
if len(pts) < 2:
    raise ValueError("Escape route requires at least 2 points")
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.add_escape_route(
    project,
    route_id=route_id,
    polyline=pts,
    width_m=width_m,
    spacing_m=spacing_m,
    height_m=height_m,
    end_margin_m=end_margin_m,
)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        route_id.trim().to_string(),
        polyline_csv,
        width_m.map(|v| v.to_string()).unwrap_or_default(),
        spacing_m.map(|v| v.to_string()).unwrap_or_default(),
        height_m.map(|v| v.to_string()).unwrap_or_default(),
        end_margin_m.map(|v| v.to_string()).unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Escape route add completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn array_luminaires_in_project(
    project_path: String,
    room_id: String,
    asset_id: String,
    rows: i64,
    cols: i64,
    margin_m: Option<f64>,
    mount_height_m: Option<f64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if room_id.trim().is_empty() || asset_id.trim().is_empty() {
        return Err("Room id and asset id are required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
room_id = sys.argv[2].strip()
asset_id = sys.argv[3].strip()
rows = int(sys.argv[4])
cols = int(sys.argv[5])
margin_m = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6].strip() else 0.5
mount_height_m = float(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7].strip() else 2.8
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.array_luminaires(
    project,
    room_id=room_id,
    asset_id=asset_id,
    rows=rows,
    cols=cols,
    margin_m=margin_m,
    mount_height_m=mount_height_m,
    approved=True,
)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        room_id.trim().to_string(),
        asset_id.trim().to_string(),
        rows.to_string(),
        cols.to_string(),
        margin_m.map(|v| v.to_string()).unwrap_or_default(),
        mount_height_m.map(|v| v.to_string()).unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Luminaire array operation completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn aim_luminaire_in_project(
    project_path: String,
    luminaire_id: String,
    yaw_deg: f64,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if luminaire_id.trim().is_empty() {
        return Err("Luminaire id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
project_path = str(Path(sys.argv[1]).expanduser().resolve())
luminaire_id = sys.argv[2].strip()
yaw_deg = float(sys.argv[3])
tools = AgentTools()
project, _ = tools.open_project(project_path)
res = tools.aim_luminaire(project, luminaire_id=luminaire_id, yaw_deg=yaw_deg, approved=True)
if res.ok:
    save_project_schema(project, Path(project_path))
print(json.dumps({"ok": res.ok, "message": res.message, "data": res.data}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        luminaire_id.trim().to_string(),
        yaw_deg.to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Luminaire aiming completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn batch_update_luminaires_in_project(
    project_path: String,
    luminaire_ids_csv: String,
    yaw_deg: Option<f64>,
    maintenance_factor: Option<f64>,
    flux_multiplier: Option<f64>,
    tilt_deg: Option<f64>,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if luminaire_ids_csv.trim().is_empty() {
        return Err("At least one luminaire id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import RotationSpec
project_path = Path(sys.argv[1]).expanduser().resolve()
ids = {x.strip() for x in sys.argv[2].split(",") if x.strip()}
yaw = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].strip() else None
maintenance = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].strip() else None
multiplier = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].strip() else None
tilt = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6].strip() else None
project = load_project_schema(project_path)
from luxera.project.history import push_snapshot
push_snapshot(project, label="batch_update_luminaires")
updated = []
for lum in project.luminaires:
    if lum.id not in ids:
        continue
    if yaw is not None:
        pitch = 0.0
        roll = 0.0
        if getattr(lum.transform.rotation, "type", None) == "euler_zyx" and getattr(lum.transform.rotation, "euler_deg", None):
            _old_yaw, pitch, roll = lum.transform.rotation.euler_deg
        lum.transform.rotation = RotationSpec(type="euler_zyx", euler_deg=(float(yaw), float(pitch), float(roll)))
    if maintenance is not None:
        lum.maintenance_factor = float(maintenance)
    if multiplier is not None:
        lum.flux_multiplier = float(multiplier)
    if tilt is not None:
        lum.tilt_deg = float(tilt)
    updated.append(lum.id)
save_project_schema(project, project_path)
print(json.dumps({"ok": True, "message": "Luminaire batch update applied", "data": {"updated_count": len(updated), "updated_ids": updated}}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        luminaire_ids_csv,
        yaw_deg.map(|v| v.to_string()).unwrap_or_default(),
        maintenance_factor.map(|v| v.to_string()).unwrap_or_default(),
        flux_multiplier.map(|v| v.to_string()).unwrap_or_default(),
        tilt_deg.map(|v| v.to_string()).unwrap_or_default(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Luminaire batch update completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn nudge_luminaire_in_project(
    project_path: String,
    luminaire_id: String,
    delta_x: f64,
    delta_y: f64,
    delta_z: f64,
    delta_yaw_deg: f64,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if luminaire_id.trim().is_empty() {
        return Err("Luminaire id is required".to_string());
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import RotationSpec
project_path = Path(sys.argv[1]).expanduser().resolve()
luminaire_id = sys.argv[2].strip()
dx = float(sys.argv[3]); dy = float(sys.argv[4]); dz = float(sys.argv[5]); dyaw = float(sys.argv[6])
project = load_project_schema(project_path)
lum = next((l for l in project.luminaires if l.id == luminaire_id), None)
if lum is None:
    print(json.dumps({"ok": False, "message": f"Luminaire not found: {luminaire_id}", "data": {}}))
    raise SystemExit(0)
from luxera.project.history import push_snapshot
push_snapshot(project, label=f"nudge_luminaire:{luminaire_id}")
px, py, pz = lum.transform.position
yaw, pitch, roll = 0.0, 0.0, 0.0
if getattr(lum.transform.rotation, "type", None) == "euler_zyx" and getattr(lum.transform.rotation, "euler_deg", None):
    yaw, pitch, roll = lum.transform.rotation.euler_deg
lum.transform.position = (float(px + dx), float(py + dy), float(pz + dz))
lum.transform.rotation = RotationSpec(type="euler_zyx", euler_deg=(float(yaw + dyaw), float(pitch), float(roll)))
save_project_schema(project, project_path)
print(json.dumps({"ok": True, "message": "Luminaire nudged", "data": {"luminaire_id": luminaire_id, "position": lum.transform.position, "yaw_deg": yaw + dyaw}}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        luminaire_id.trim().to_string(),
        delta_x.to_string(),
        delta_y.to_string(),
        delta_z.to_string(),
        delta_yaw_deg.to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Luminaire nudge completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn transform_opening_in_project(
    project_path: String,
    opening_id: String,
    delta_x: f64,
    delta_y: f64,
    delta_z: f64,
    delta_yaw_deg: f64,
) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    if opening_id.trim().is_empty() {
        return Err("Opening id is required".to_string());
    }
    let script = r#"
import json, math, sys
from pathlib import Path
from luxera.project.io import load_project_schema, save_project_schema
project_path = Path(sys.argv[1]).expanduser().resolve()
opening_id = sys.argv[2].strip()
dx = float(sys.argv[3]); dy = float(sys.argv[4]); dz = float(sys.argv[5]); dyaw = float(sys.argv[6])
project = load_project_schema(project_path)
op = next((o for o in project.geometry.openings if o.id == opening_id), None)
if op is None:
    print(json.dumps({"ok": False, "message": f"Opening not found: {opening_id}", "data": {}}))
    raise SystemExit(0)
from luxera.project.history import push_snapshot
push_snapshot(project, label=f"transform_opening:{opening_id}")
verts = [(float(v[0]), float(v[1]), float(v[2])) for v in (op.vertices or [])]
if not verts:
    print(json.dumps({"ok": False, "message": f"Opening has no vertices: {opening_id}", "data": {}}))
    raise SystemExit(0)
cx = sum(v[0] for v in verts) / len(verts)
cy = sum(v[1] for v in verts) / len(verts)
theta = math.radians(dyaw)
ct = math.cos(theta); st = math.sin(theta)
out = []
for x, y, z in verts:
    rx = x - cx
    ry = y - cy
    xr = cx + rx * ct - ry * st
    yr = cy + rx * st + ry * ct
    out.append((float(xr + dx), float(yr + dy), float(z + dz)))
op.vertices = out
save_project_schema(project, project_path)
print(json.dumps({"ok": True, "message": "Opening transformed", "data": {"opening_id": opening_id, "vertex_count": len(out)}}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
        opening_id.trim().to_string(),
        delta_x.to_string(),
        delta_y.to_string(),
        delta_z.to_string(),
        delta_yaw_deg.to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Opening transform completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        None
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn undo_project_change(project_path: String) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.history import undo as undo_project_history
project_path = Path(sys.argv[1]).expanduser().resolve()
project = load_project_schema(project_path)
ok = undo_project_history(project)
if ok:
    save_project_schema(project, project_path)
print(json.dumps({
    "ok": bool(ok),
    "message": "Undo applied" if ok else "No undo snapshot available",
    "data": {
        "undo_depth": len(getattr(project, "assistant_undo_stack", []) or []),
        "redo_depth": len(getattr(project, "assistant_redo_stack", []) or []),
    },
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Undo operation completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn redo_project_change(project_path: String) -> Result<ToolOperationResult, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let project = resolve_repo_relative(&PathBuf::from(project_path.trim()), &cwd)?;
    if !project.exists() || !project.is_file() {
        return Err(format!("Project file not found: {}", project.display()));
    }
    let script = r#"
import json, sys
from pathlib import Path
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.history import redo as redo_project_history
project_path = Path(sys.argv[1]).expanduser().resolve()
project = load_project_schema(project_path)
ok = redo_project_history(project)
if ok:
    save_project_schema(project, project_path)
print(json.dumps({
    "ok": bool(ok),
    "message": "Redo applied" if ok else "No redo snapshot available",
    "data": {
        "undo_depth": len(getattr(project, "assistant_undo_stack", []) or []),
        "redo_depth": len(getattr(project, "assistant_redo_stack", []) or []),
    },
}))
"#;
    let payload = run_python_json(&[
        "-c".to_string(),
        script.to_string(),
        project.to_string_lossy().to_string(),
    ])?;
    let success = payload.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
    let message = payload
        .get("message")
        .and_then(|x| x.as_str())
        .unwrap_or("Redo operation completed")
        .to_string();
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let project_doc = if success {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    } else {
        Some(open_project_file(project.to_string_lossy().to_string())?)
    };
    Ok(ToolOperationResult {
        success,
        message,
        data,
        project: project_doc,
    })
}

#[tauri::command]
fn run_project_job(project_path: String, job_id: String) -> Result<JobRunResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    if !resolved_project.exists() || !resolved_project.is_file() {
        return Err(format!("Project file not found: {}", resolved_project.display()));
    }
    let job = job_id.trim();
    if job.is_empty() {
        return Err("Job id is empty".to_string());
    }

    let repo_root = find_repo_root(&cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    let python = resolve_python_executable();
    let output = Command::new(&python)
        .arg("-m")
        .arg("luxera.cli")
        .arg("run")
        .arg(resolved_project.to_string_lossy().to_string())
        .arg(job)
        .current_dir(&repo_root)
        .output()
        .map_err(|e| format!("Failed to execute Luxera runner via {}: {}", python, e))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let success = output.status.success();
    let exit_code = output.status.code().unwrap_or(-1);
    let result_dir = parse_result_dir(&stdout, &stderr);

    Ok(JobRunResponse {
        project_path: resolved_project.to_string_lossy().to_string(),
        job_id: job.to_string(),
        success,
        exit_code,
        stdout,
        stderr,
        result_dir,
    })
}

#[tauri::command]
fn start_project_job_run(project_path: String, job_id: String) -> Result<JobRunStartResponse, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_project = PathBuf::from(project_path.trim());
    if raw_project.as_os_str().is_empty() {
        return Err("Project path is empty".to_string());
    }
    let resolved_project = resolve_repo_relative(&raw_project, &cwd)?;
    if !resolved_project.exists() || !resolved_project.is_file() {
        return Err(format!("Project file not found: {}", resolved_project.display()));
    }
    let job = job_id.trim();
    if job.is_empty() {
        return Err("Job id is empty".to_string());
    }

    let repo_root = find_repo_root(&cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    let python = resolve_python_executable();
    let mut child = Command::new(&python)
        .arg("-m")
        .arg("luxera.cli")
        .arg("run")
        .arg(resolved_project.to_string_lossy().to_string())
        .arg(job)
        .current_dir(&repo_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to execute Luxera runner via {}: {}", python, e))?;

    let stdout_buf = Arc::new(Mutex::new(String::new()));
    let stderr_buf = Arc::new(Mutex::new(String::new()));
    if let Some(stdout) = child.stdout.take() {
        spawn_stream_reader(stdout, Arc::clone(&stdout_buf));
    }
    if let Some(stderr) = child.stderr.take() {
        spawn_stream_reader(stderr, Arc::clone(&stderr_buf));
    }

    let run_id = next_run_id();
    let mut runs = running_jobs()
        .lock()
        .map_err(|_| "Running jobs registry lock poisoned".to_string())?;
    runs.insert(
        run_id,
        RunningJob {
            child,
            stdout_buf,
            stderr_buf,
        },
    );
    Ok(JobRunStartResponse {
        run_id,
        project_path: resolved_project.to_string_lossy().to_string(),
        job_id: job.to_string(),
    })
}

#[tauri::command]
fn poll_project_job_run(run_id: u64) -> Result<JobRunPollResponse, String> {
    let mut runs = running_jobs()
        .lock()
        .map_err(|_| "Running jobs registry lock poisoned".to_string())?;
    let Some(run) = runs.get_mut(&run_id) else {
        return Err(format!("Unknown run id: {}", run_id));
    };

    let stdout = run
        .stdout_buf
        .lock()
        .map_err(|_| "stdout buffer lock poisoned".to_string())?
        .clone();
    let stderr = run
        .stderr_buf
        .lock()
        .map_err(|_| "stderr buffer lock poisoned".to_string())?
        .clone();

    if let Some(status) = run.child.try_wait().map_err(|e| format!("Failed polling run {}: {}", run_id, e))? {
        let success = status.success();
        let exit_code = status.code().unwrap_or(-1);
        let result_dir = parse_result_dir(&stdout, &stderr);
        runs.remove(&run_id);
        return Ok(JobRunPollResponse {
            run_id,
            done: true,
            success,
            exit_code,
            stdout,
            stderr,
            result_dir,
        });
    }

    Ok(JobRunPollResponse {
        run_id,
        done: false,
        success: false,
        exit_code: 0,
        stdout,
        stderr,
        result_dir: None,
    })
}

#[tauri::command]
fn cancel_project_job_run(run_id: u64) -> Result<JobRunPollResponse, String> {
    let mut runs = running_jobs()
        .lock()
        .map_err(|_| "Running jobs registry lock poisoned".to_string())?;
    let Some(mut run) = runs.remove(&run_id) else {
        return Err(format!("Unknown run id: {}", run_id));
    };

    let _ = run.child.kill();
    let _ = run.child.wait();
    let stdout = run
        .stdout_buf
        .lock()
        .map_err(|_| "stdout buffer lock poisoned".to_string())?
        .clone();
    let stderr = run
        .stderr_buf
        .lock()
        .map_err(|_| "stderr buffer lock poisoned".to_string())?
        .clone();
    let result_dir = parse_result_dir(&stdout, &stderr);

    Ok(JobRunPollResponse {
        run_id,
        done: true,
        success: false,
        exit_code: -9,
        stdout,
        stderr,
        result_dir,
    })
}

#[tauri::command]
fn list_recent_runs(limit: Option<usize>) -> Result<Vec<RecentRun>, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let repo_root = find_repo_root(&cwd)
        .ok_or_else(|| "Could not locate repository root (pyproject.toml) from current directory".to_string())?;
    let out_dir = repo_root.join("out");
    if !out_dir.exists() {
        return Ok(vec![]);
    }
    let max_items = limit.unwrap_or(20).max(1).min(200);
    let mut runs: Vec<RecentRun> = Vec::new();

    let entries = fs::read_dir(&out_dir).map_err(|e| format!("Failed to scan {}: {}", out_dir.display(), e))?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let result_path = path.join("result.json");
        if !result_path.exists() {
            continue;
        }
        let modified_unix_s = run_modified_unix_seconds(&result_path);
        let mut job_id = None;
        let mut job_type = None;
        let mut contract_version = None;
        if let Ok(raw) = fs::read_to_string(&result_path) {
            if let Ok(v) = serde_json::from_str::<Value>(&raw) {
                contract_version = v
                    .get("contract_version")
                    .and_then(|x| x.as_str())
                    .map(|x| x.to_string());
                job_id = v.get("job_id").and_then(|x| x.as_str()).map(|x| x.to_string());
                job_type = v
                    .get("job")
                    .and_then(|x| x.as_object())
                    .and_then(|j| j.get("type"))
                    .and_then(|x| x.as_str())
                    .map(|x| x.to_string());
            }
        }
        runs.push(RecentRun {
            result_dir: path.to_string_lossy().to_string(),
            modified_unix_s,
            job_id,
            job_type,
            contract_version,
        });
    }
    runs.sort_by(|a, b| b.modified_unix_s.cmp(&a.modified_unix_s));
    runs.truncate(max_items);
    Ok(runs)
}

#[tauri::command]
fn read_artifact(path: String, max_bytes: Option<usize>) -> Result<ArtifactRead, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_path = PathBuf::from(path.trim());
    if raw_path.as_os_str().is_empty() {
        return Err("Artifact path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw_path, &cwd)?;
    let meta = fs::metadata(&resolved).map_err(|e| format!("Cannot stat {}: {}", resolved.display(), e))?;
    if !meta.is_file() {
        return Err(format!("Artifact is not a file: {}", resolved.display()));
    }
    let max_len = max_bytes.unwrap_or(512_000).max(1).min(5_000_000);
    let bytes = fs::read(&resolved).map_err(|e| format!("Cannot read {}: {}", resolved.display(), e))?;
    let truncated = bytes.len() > max_len;
    let slice = if truncated { &bytes[..max_len] } else { &bytes[..] };
    let content = String::from_utf8_lossy(slice).to_string();
    Ok(ArtifactRead {
        path: resolved.to_string_lossy().to_string(),
        size_bytes: meta.len(),
        truncated,
        content,
    })
}

#[tauri::command]
fn read_artifact_binary(path: String, max_bytes: Option<usize>) -> Result<ArtifactBinaryRead, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_path = PathBuf::from(path.trim());
    if raw_path.as_os_str().is_empty() {
        return Err("Artifact path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw_path, &cwd)?;
    let meta = fs::metadata(&resolved).map_err(|e| format!("Cannot stat {}: {}", resolved.display(), e))?;
    if !meta.is_file() {
        return Err(format!("Artifact is not a file: {}", resolved.display()));
    }
    let max_len = max_bytes.unwrap_or(2_000_000).max(1).min(10_000_000);
    let bytes = fs::read(&resolved).map_err(|e| format!("Cannot read {}: {}", resolved.display(), e))?;
    let truncated = bytes.len() > max_len;
    let slice = if truncated { &bytes[..max_len] } else { &bytes[..] };
    let data_base64 = general_purpose::STANDARD.encode(slice);
    Ok(ArtifactBinaryRead {
        path: resolved.to_string_lossy().to_string(),
        size_bytes: meta.len(),
        truncated,
        mime_type: mime_for_path(&resolved).to_string(),
        data_base64,
    })
}

#[tauri::command]
fn list_result_artifacts(result_dir: String, limit: Option<usize>) -> Result<Vec<ArtifactEntry>, String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_path = PathBuf::from(result_dir.trim());
    if raw_path.as_os_str().is_empty() {
        return Err("Result directory path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw_path, &cwd)?;
    if !resolved.exists() || !resolved.is_dir() {
        return Err(format!("Directory not found: {}", resolved.display()));
    }
    let mut artifacts: Vec<ArtifactEntry> = Vec::new();
    collect_artifacts(&resolved, &resolved, &mut artifacts)?;
    artifacts.sort_by(|a, b| {
        b.modified_unix_s
            .cmp(&a.modified_unix_s)
            .then_with(|| a.relative_path.cmp(&b.relative_path))
    });
    artifacts.truncate(limit.unwrap_or(200).max(1).min(2000));
    Ok(artifacts)
}

#[tauri::command]
fn open_result_dir(path: String) -> Result<(), String> {
    let cwd = std::env::current_dir().map_err(|e| format!("Cannot resolve current directory: {}", e))?;
    let raw_path = PathBuf::from(path.trim());
    if raw_path.as_os_str().is_empty() {
        return Err("Result directory path is empty".to_string());
    }
    let resolved = resolve_repo_relative(&raw_path, &cwd)?;
    if !resolved.exists() || !resolved.is_dir() {
        return Err(format!("Directory not found: {}", resolved.display()));
    }
    #[cfg(target_os = "macos")]
    let mut cmd = {
        let mut c = Command::new("open");
        c.arg(&resolved);
        c
    };
    #[cfg(target_os = "linux")]
    let mut cmd = {
        let mut c = Command::new("xdg-open");
        c.arg(&resolved);
        c
    };
    #[cfg(target_os = "windows")]
    let mut cmd = {
        let mut c = Command::new("explorer");
        c.arg(&resolved);
        c
    };
    cmd.spawn()
        .map_err(|e| format!("Failed to open {}: {}", resolved.display(), e))?;
    Ok(())
}

#[tauri::command]
fn desktop_backend_contract() -> Value {
    json!({
        "contract_version": "desktop_backend_v1",
        "required_files": ["result.json"],
        "optional_files": ["tables.json", "results.json", "road_summary.json", "roadway_submission.json"],
        "rendered_sections": ["summary", "warnings", "compliance", "tables", "results_engines", "roadway_submission_typed", "artifact_inventory", "artifact_image_preview", "raw_json_explorer"],
        "max_read_artifact_bytes_default": 512000
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            load_backend_outputs,
            get_falsecolor_grid_data,
            init_project_file,
            open_project_file,
            save_project_file,
            validate_project_file,
            add_room_to_project,
            import_geometry_to_project,
            clean_geometry_in_project,
            add_photometry_to_project,
            verify_photometry_file_input,
            verify_project_photometry_asset,
            get_photometry_polar_data,
            get_luminaire_beam_data,
            add_luminaire_to_project,
            add_grid_to_project,
            add_job_to_project,
            list_standard_profiles,
            set_compliance_profile_in_project,
            evaluate_compliance_detailed,
            estimate_illuminance_fast,
            propose_quick_layout,
            apply_quick_layout,
            export_debug_bundle,
            export_client_bundle,
            export_backend_compare,
            export_roadway_report,
            execute_agent_intent,
            execute_agent_turn,
            assign_material_in_project,
            add_project_variant,
            compare_project_variants,
            compare_variants_visual,
            propose_project_optimizations,
            apply_project_optimization_option,
            edit_room_in_project,
            set_daylight_aperture_in_project,
            add_escape_route_in_project,
            array_luminaires_in_project,
            aim_luminaire_in_project,
            batch_update_luminaires_in_project,
            nudge_luminaire_in_project,
            transform_opening_in_project,
            undo_project_change,
            redo_project_change,
            list_project_jobs,
            run_project_job,
            start_project_job_run,
            poll_project_job_run,
            cancel_project_job_run,
            list_recent_runs,
            load_recent_projects_store,
            save_recent_projects_store,
            read_artifact,
            read_artifact_binary,
            list_result_artifacts,
            open_result_dir,
            desktop_backend_contract,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
