from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple
import zipfile

from luxera.core.hashing import sha256_bytes, sha256_file
from luxera.project.schema import Project, JobResultRef


def export_debug_bundle(project: Project, job_ref: JobResultRef, out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result_dir = Path(job_ref.result_dir)
    files: List[Tuple[Path, str]] = []
    bundle_entries: List[Dict[str, object]] = []

    # Project file
    if project.root_dir:
        project_file = Path(project.root_dir) / "project.json"
        if project_file.exists():
            files.append((project_file, "project.file.json"))

    # Result artifacts
    for p in result_dir.glob("*"):
        if p.is_file():
            files.append((p, p.name))

    # Photometry assets
    for asset in project.photometry_assets:
        if asset.path:
            p = Path(asset.path)
            if p.exists():
                files.append((p, f"assets/{asset.id}_{p.name}"))

    project_snapshot = json.dumps(project.to_dict(), indent=2, sort_keys=True).encode("utf-8")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_arcnames = set()
        for f, arcname in files:
            if arcname in seen_arcnames:
                continue
            seen_arcnames.add(arcname)
            zf.write(f, arcname)
            bundle_entries.append(
                {
                    "path": arcname,
                    "sha256": sha256_file(str(f)),
                    "size_bytes": f.stat().st_size,
                }
            )

        zf.writestr("project.snapshot.json", project_snapshot)
        bundle_entries.append(
            {
                "path": "project.snapshot.json",
                "sha256": sha256_bytes(project_snapshot),
                "size_bytes": len(project_snapshot),
            }
        )

        manifest = {
            "bundle_contract_version": "debug_bundle_v1",
            "job_id": job_ref.job_id,
            "job_hash": job_ref.job_hash,
            "result_dir": str(result_dir),
            "entries": bundle_entries,
        }
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        zf.writestr("bundle_manifest.json", manifest_bytes)

    return out_path
