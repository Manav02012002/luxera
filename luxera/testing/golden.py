from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import luxera

from luxera.runner import run_job


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    project_path: Path
    scene_path: Path
    expected_dir: Path
    run_settings: Dict[str, object]
    tolerances: Dict[str, float]
    metadata: Dict[str, object]

    @property
    def metadata_path(self) -> Path:
        return self.expected_dir / "metadata.json"

    @property
    def job_id(self) -> str:
        value = self.run_settings.get("job_id")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Golden case {self.case_id} has invalid run_settings.job_id")
        return value


def default_golden_root() -> Path:
    # Repository-relative default.
    return Path("tests/golden").resolve()


def _coerce_tolerances(raw: object) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                out[str(k)] = float(v)
    return out


def _load_case_metadata(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data) if isinstance(data, dict) else {}


def load_golden_case(case_id: str, root: Optional[Path] = None) -> GoldenCase:
    root_dir = (root or default_golden_root()).expanduser().resolve()
    project_path = root_dir / "projects" / case_id / "project.json"
    scene_path = root_dir / "scenes" / case_id / "scene.json"
    expected_dir = root_dir / "expected" / case_id
    metadata = _load_case_metadata(expected_dir / "metadata.json")
    run_settings = metadata.get("run_settings", {})
    if not isinstance(run_settings, dict):
        run_settings = {}
    tolerances = _coerce_tolerances(metadata.get("tolerances", {}))
    if not tolerances:
        tolerances = {
            "max_abs_lux": 1e-6,
            "mean_rel": 1e-6,
            "p95_abs_lux": 1e-6,
        }
    return GoldenCase(
        case_id=case_id,
        project_path=project_path,
        scene_path=scene_path,
        expected_dir=expected_dir,
        run_settings=dict(run_settings),
        tolerances=tolerances,
        metadata=metadata,
    )


def discover_golden_cases(root: Optional[Path] = None) -> List[GoldenCase]:
    root_dir = (root or default_golden_root()).expanduser().resolve()
    projects_dir = root_dir / "projects"
    if not projects_dir.exists():
        return []
    out: List[GoldenCase] = []
    for p in sorted(projects_dir.iterdir()):
        if not p.is_dir():
            continue
        case_id = p.name
        out.append(load_golden_case(case_id, root=root_dir))
    return out


def run_golden_case(case: GoldenCase, run_root: Optional[Path] = None) -> Path:
    if not case.project_path.exists():
        raise FileNotFoundError(f"Golden project not found: {case.project_path}")
    if not case.scene_path.exists():
        raise FileNotFoundError(f"Golden scene file not found: {case.scene_path}")
    ref = run_job(case.project_path, case.job_id)
    result_dir = Path(ref.result_dir).expanduser().resolve()
    out_root = run_root.expanduser().resolve() if run_root is not None else case.expected_dir.parent.parent / "runs"
    out_dir = out_root / case.case_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(result_dir, out_dir)
    meta = dict(case.metadata)
    meta.setdefault("case_id", case.case_id)
    meta.setdefault("run_settings", dict(case.run_settings))
    meta.setdefault("tolerances", dict(case.tolerances))
    meta.setdefault("tolerance_policy", "strict")
    meta.setdefault("engine_version", getattr(luxera, "__version__", "unknown"))
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return out_dir
