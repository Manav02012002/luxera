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
        _ => "application/octet-stream",
    }
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
        .invoke_handler(tauri::generate_handler![
            load_backend_outputs,
            list_project_jobs,
            run_project_job,
            start_project_job_run,
            poll_project_job_run,
            cancel_project_job_run,
            list_recent_runs,
            read_artifact,
            read_artifact_binary,
            list_result_artifacts,
            open_result_dir,
            desktop_backend_contract,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
