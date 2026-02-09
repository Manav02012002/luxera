from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from luxera.agent.audit import append_audit_event
from luxera.agent.tools.api import AgentTools


@dataclass(frozen=True)
class RuntimeAction:
    kind: str
    requires_approval: bool
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeResponse:
    plan: str
    diff_preview: Dict[str, Any]
    run_manifest: Dict[str, Any]
    actions: List[RuntimeAction]
    produced_artifacts: List[str]
    warnings: List[str]
    compliance_claimed: bool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["actions"] = [asdict(a) for a in self.actions]
        return d


class AgentRuntime:
    def __init__(self, tools: Optional[AgentTools] = None):
        self.tools = tools or AgentTools()

    def _memory_path(self, project_path: Path) -> Path:
        root = project_path.parent / ".luxera"
        root.mkdir(parents=True, exist_ok=True)
        return root / "agent_memory.json"

    def _load_memory(self, project_path: Path) -> Dict[str, Any]:
        p = self._memory_path(project_path)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_memory(self, project_path: Path, memory: Dict[str, Any]) -> None:
        p = self._memory_path(project_path)
        p.write_text(json.dumps(memory, indent=2, sort_keys=True), encoding="utf-8")

    def _deterministic_id(self, project_name: str, intent: str) -> str:
        h = hashlib.sha256(f"{project_name}\n{intent.strip().lower()}".encode("utf-8")).hexdigest()
        return h[:16]

    def execute(
        self,
        project_path: str,
        intent: str,
        approvals: Optional[Dict[str, bool]] = None,
    ) -> RuntimeResponse:
        approvals = approvals or {}
        project, ppath = self.tools.open_project(project_path)
        memory = self._load_memory(ppath)
        lintent = intent.strip().lower()
        warnings: List[str] = []
        produced: List[str] = []
        actions: List[RuntimeAction] = []
        tool_calls: List[Dict[str, Any]] = []
        compliance_claimed = False

        runtime_id = self._deterministic_id(project.name, intent)
        plan = "Interpret intent, propose diff if needed, require approvals for apply/run, and produce artifacts."
        run_manifest: Dict[str, Any] = {"runtime_id": runtime_id, "intent": intent, "project": project.name}
        diff_preview: Dict[str, Any] = {"ops": [], "count": 0}

        if "place" in lintent or "layout" in lintent or "target" in lintent:
            target = memory.get("preferred_target_lux", 500.0)
            for tok in lintent.replace("/", " ").split():
                try:
                    target = float(tok)
                except ValueError:
                    continue
            memory["preferred_target_lux"] = target
            pr = self.tools.propose_layout_diff(project, target, constraints={"max_rows": 6, "max_cols": 6})
            tool_calls.append({"tool": "propose_layout_diff", "target_lux": target})
            diff = pr.data["diff"]
            diff_preview = pr.data["preview"]
            actions.append(RuntimeAction(kind="apply_diff", requires_approval=True, payload={"op_count": diff_preview.get("count", 0)}))
            if approvals.get("apply_diff", False):
                r = self.tools.apply_diff(project, diff, approved=True)
                tool_calls.append({"tool": "apply_diff", "approved": True})
                if not r.ok:
                    warnings.append(r.message)

        if "import" in lintent:
            # command style: /import <path>
            tokens = intent.strip().split()
            if len(tokens) >= 2:
                file_path = tokens[1]
                ir = self.tools.import_geometry(project, file_path=file_path)
                tool_calls.append({"tool": "import_geometry", "file_path": file_path})
                if not ir.ok:
                    warnings.append(ir.message)
            else:
                warnings.append("Import intent requires file path.")

        if "detect rooms" in lintent or "clean geometry" in lintent:
            cg = self.tools.clean_geometry(project, detect_rooms=True)
            tool_calls.append({"tool": "clean_geometry", "detect_rooms": True})
            if not cg.ok:
                warnings.append(cg.message)

        if lintent.startswith("/grid") or "grid workplane" in lintent:
            # Simple command: /grid <elevation> <spacing>
            elevation = 0.8
            spacing = 0.25
            parts = lintent.split()
            nums: List[float] = []
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    continue
            if len(nums) >= 1:
                elevation = nums[0]
            if len(nums) >= 2:
                spacing = nums[1]
            room = project.geometry.rooms[0] if project.geometry.rooms else None
            width = room.width if room else 6.0
            height = room.length if room else 8.0
            nx = max(2, int(round(width / max(spacing, 0.1))) + 1)
            ny = max(2, int(round(height / max(spacing, 0.1))) + 1)
            gr = self.tools.add_grid(project, name="Agent Grid", width=width, height=height, elevation=elevation, nx=nx, ny=ny)
            tool_calls.append({"tool": "add_grid", "name": "Agent Grid", "elevation": elevation, "spacing": spacing, "nx": nx, "ny": ny})
            if not gr.ok:
                warnings.append(gr.message)

        if "optimizer" in lintent or "optimize" in lintent:
            # Use layout proposer as deterministic optimizer baseline.
            target = memory.get("preferred_target_lux", 500.0)
            pr = self.tools.propose_layout_diff(project, target_lux=float(target), constraints={"max_rows": 8, "max_cols": 8})
            tool_calls.append({"tool": "propose_layout_diff", "target_lux": float(target), "mode": "optimizer"})
            if pr.ok:
                diff_preview = pr.data["preview"]
                diff = pr.data["diff"]
                actions.append(RuntimeAction(kind="apply_diff", requires_approval=True, payload={"op_count": diff_preview.get("count", 0), "mode": "optimizer"}))
                if approvals.get("apply_diff", False):
                    ar = self.tools.apply_diff(project, diff, approved=True)
                    tool_calls.append({"tool": "apply_diff", "approved": True, "mode": "optimizer"})
                    if not ar.ok:
                        warnings.append(ar.message)
            else:
                warnings.append(pr.message)

        if "run" in lintent:
            # Choose first job unless explicit id token is present.
            job_id = project.jobs[0].id if project.jobs else ""
            tokens = lintent.split()
            for i, t in enumerate(tokens):
                if t == "job" and i + 1 < len(tokens):
                    job_id = tokens[i + 1]
            if not job_id:
                warnings.append("No job found to run.")
            else:
                actions.append(RuntimeAction(kind="run_job", requires_approval=True, payload={"job_id": job_id}))
                if approvals.get("run_job", False):
                    rr = self.tools.run_job(project, job_id=job_id, approved=True)
                    tool_calls.append({"tool": "run_job", "job_id": job_id, "approved": True})
                    run_manifest["run_result"] = rr.data
                    if rr.ok:
                        produced.append(rr.data.get("result_dir", ""))
                    else:
                        warnings.append(rr.message)

        if "report" in lintent:
            if not project.results:
                warnings.append("Cannot export report: no job results available.")
            else:
                job_id = project.results[-1].job_id
                if "client" in lintent:
                    out_zip = str(ppath.parent / f"{project.name}_client_bundle.zip")
                    rc = self.tools.export_client_bundle(project, job_id, out_zip)
                    tool_calls.append({"tool": "export_client_bundle", "job_id": job_id, "out": out_zip})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)
                elif "debug" in lintent:
                    out_zip = str(ppath.parent / f"{project.name}_debug_bundle.zip")
                    rc = self.tools.export_debug_bundle(project, job_id, out_zip)
                    tool_calls.append({"tool": "export_debug_bundle", "job_id": job_id, "out": out_zip})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)
                else:
                    out_pdf = str(ppath.parent / f"{project.name}_{job_id}_en12464.pdf")
                    rc = self.tools.build_pdf(project, job_id=job_id, report_type="en12464", out_path=out_pdf)
                    tool_calls.append({"tool": "build_pdf", "job_id": job_id, "report_type": "en12464", "out": out_pdf})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)

        if "heatmap" in lintent:
            if not project.results:
                warnings.append("Cannot render heatmap: no job results available.")
            else:
                job_id = project.results[-1].job_id
                hm = self.tools.render_heatmap(project, job_id=job_id)
                tool_calls.append({"tool": "render_heatmap", "job_id": job_id})
                if hm.ok:
                    produced.extend(list((hm.data.get("artifacts") or {}).values()))
                else:
                    warnings.append(hm.message)

        if "summarize" in lintent or "summary" in lintent:
            if project.results:
                job_id = project.results[-1].job_id
                sm = self.tools.summarize_results(project, job_id=job_id)
                tool_calls.append({"tool": "summarize_results", "job_id": job_id})
                if sm.ok:
                    run_manifest["latest_summary"] = sm.data.get("summary", {})
                else:
                    warnings.append(sm.message)

        if "compliance" in lintent:
            # Guardrail: no compliance claim without executed result.
            compliance_claimed = False
            if not project.results:
                warnings.append("Compliance cannot be declared without running jobs.")
                if project.jobs:
                    actions.append(RuntimeAction(kind="run_job", requires_approval=True, payload={"job_id": project.jobs[0].id, "reason": "compliance_assistant"}))
            else:
                run_manifest["compliance_source_job"] = project.results[-1].job_id
                latest = project.results[-1]
                summary = latest.summary or {}
                comp = summary.get("compliance")
                run_manifest["compliance_summary"] = comp
                if isinstance(comp, str) and "NON-COMPLIANT" in comp:
                    warnings.append("Latest result is non-compliant; proposing corrective layout diff.")

        append_audit_event(
            project,
            action="agent.runtime.execute",
            plan=plan,
            tool_calls=tool_calls + [{"actions": [asdict(a) for a in actions]}],
            artifacts=produced,
            warnings=warnings,
            metadata={"runtime_id": runtime_id, "intent": intent},
        )
        self.tools.save_project(project, ppath)
        self._save_memory(ppath, memory)

        return RuntimeResponse(
            plan=plan,
            diff_preview=diff_preview,
            run_manifest=run_manifest,
            actions=actions,
            produced_artifacts=produced,
            warnings=warnings,
            compliance_claimed=compliance_claimed,
        )
