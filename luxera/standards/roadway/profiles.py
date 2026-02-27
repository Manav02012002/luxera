from __future__ import annotations
"""Contract: docs/spec/roadway_profiles.md."""

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Tuple


Comparator = Literal[">=", "<="]


@dataclass(frozen=True)
class RoadwayRequirement:
    metric: str
    comparator: Comparator
    target: float
    units: str


@dataclass(frozen=True)
class RoadwayProfile:
    id: str
    name: str
    standard_ref: str
    domain: str
    roadway_class: str
    notes: str
    requirements: List[RoadwayRequirement]


def _data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _root_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_requirements_from_table(path: Path, *, profile_id: str) -> List[RoadwayRequirement]:
    if not path.exists():
        raise FileNotFoundError(f"Roadway requirements table not found: {path}")
    rows: List[RoadwayRequirement] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            rows.append(
                RoadwayRequirement(
                    metric=str(row["metric"]).strip(),
                    comparator=str(row["comparator"]).strip(),  # type: ignore[arg-type]
                    target=float(row["target"]),
                    units=str(row.get("units", "")),
                )
            )
    if not rows:
        raise ValueError(f"Roadway requirements table is empty for profile '{profile_id}': {path}")
    return sorted(rows, key=lambda r: r.metric)


@lru_cache(maxsize=1)
def _load_profiles() -> Dict[str, RoadwayProfile]:
    root = _root_dir()
    profiles_json = root / "profiles.json"
    out: Dict[str, RoadwayProfile] = {}

    if profiles_json.exists():
        cfg = json.loads(profiles_json.read_text(encoding="utf-8"))
        for p in cfg.get("profiles", []):
            pid = str(p["id"]).strip()
            table_rel = str(p.get("requirements_table", "")).strip()
            if not table_rel:
                raise ValueError(f"Profile '{pid}' is missing requirements_table")
            req_table = (root / table_rel).resolve()
            reqs = _load_requirements_from_table(req_table, profile_id=pid)
            out[pid] = RoadwayProfile(
                id=pid,
                name=str(p.get("name", pid)),
                standard_ref=str(p.get("standard_ref", "")),
                domain=str(p.get("domain", "roadway")),
                roadway_class=str(p.get("class", "")),
                notes=str(p.get("notes", "")),
                requirements=reqs,
            )
        return dict(sorted(out.items(), key=lambda kv: kv[0]))

    # Backward-compat fallback.
    data_root = _data_dir()
    cfg = json.loads((data_root / "profile_configs.json").read_text(encoding="utf-8"))
    req_rows: Dict[str, List[RoadwayRequirement]] = {}
    with (data_root / "requirements_table.csv").open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            pid = str(row["profile_id"]).strip()
            req_rows.setdefault(pid, []).append(
                RoadwayRequirement(
                    metric=str(row["metric"]).strip(),
                    comparator=str(row["comparator"]).strip(),  # type: ignore[arg-type]
                    target=float(row["target"]),
                    units=str(row.get("units", "")),
                )
            )
    for p in cfg.get("profiles", []):
        pid = str(p["id"])
        out[pid] = RoadwayProfile(
            id=pid,
            name=str(p.get("name", pid)),
            standard_ref=str(p.get("standard_ref", "")),
            domain=str(p.get("domain", "roadway")),
            roadway_class=str(p.get("class", "")),
            notes=str(p.get("notes", "")),
            requirements=sorted(req_rows.get(pid, []), key=lambda r: r.metric),
        )
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def list_profiles() -> List[RoadwayProfile]:
    return sorted(_load_profiles().values(), key=lambda p: p.id)


def get_profile(profile_id: str) -> RoadwayProfile:
    profiles = _load_profiles()
    pid = str(profile_id).strip()
    if pid not in profiles:
        raise KeyError(f"Unknown roadway profile: {pid}")
    return profiles[pid]


def evaluate_roadway_profile(profile: RoadwayProfile, summary: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object]]:
    checks: List[Dict[str, object]] = []
    all_pass = True
    for req in profile.requirements:
        actual = float(summary.get(req.metric, 0.0) or 0.0)
        if req.comparator == ">=":
            passed = actual >= req.target
            margin = actual - req.target
        else:
            passed = actual <= req.target
            margin = req.target - actual
        all_pass = all_pass and passed
        checks.append(
            {
                "metric": req.metric,
                "comparator": req.comparator,
                "target": req.target,
                "actual": actual,
                "margin": float(margin),
                "pass": bool(passed),
                "units": req.units,
            }
        )
    checks.sort(key=lambda c: str(c.get("metric", "")))
    status = "PASS" if all_pass else "FAIL"

    by_metric = {str(c["metric"]): c for c in checks}
    thresholds = {str(c["metric"]): float(c["target"]) for c in checks}
    margins = {str(c["metric"]): float(c["margin"]) for c in checks}

    compliance = {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "standard": profile.standard_ref,
        "class": profile.roadway_class,
        "status": status,
        "checks": checks,
        "thresholds": thresholds,
        "margins": margins,
        "avg_ok": bool(by_metric.get("mean_lux", {}).get("pass", False)),
        "uo_ok": bool(by_metric.get("uniformity_ratio", {}).get("pass", False)),
        "ul_ok": bool(by_metric.get("ul_longitudinal", {}).get("pass", False)),
        "luminance_ok": bool(by_metric.get("road_luminance_mean_cd_m2", {}).get("pass", False)),
        "ti_ok": bool(by_metric.get("threshold_increment_ti_proxy_percent", {}).get("pass", False)),
        "surround_ratio_ok": bool(by_metric.get("surround_ratio_proxy", {}).get("pass", False)),
    }

    submission = {
        "title": "Roadway Submission Summary",
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "standard_ref": profile.standard_ref,
            "class": profile.roadway_class,
            "notes": profile.notes,
        },
        "status": status,
        "checks": checks,
        "overall": {
            "mean_lux": float(summary.get("mean_lux", 0.0) or 0.0),
            "uniformity_ratio": float(summary.get("uniformity_ratio", 0.0) or 0.0),
            "ul_longitudinal": float(summary.get("ul_longitudinal", 0.0) or 0.0),
            "road_luminance_mean_cd_m2": float(summary.get("road_luminance_mean_cd_m2", 0.0) or 0.0),
            "threshold_increment_ti_proxy_percent": float(summary.get("threshold_increment_ti_proxy_percent", 0.0) or 0.0),
        },
    }
    return compliance, submission
