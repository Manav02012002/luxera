from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from luxera.agent.audit import append_audit_event
from luxera.agent.tools.api import AgentTools
from luxera.agent.tools.registry import AgentToolRegistry, build_default_registry
from luxera.agent.types import AgentPlan, AgentSessionLog, ProjectDiff as AgentProjectDiff, RunManifest
from luxera.project.diff import ProjectDiff, DiffOp
from luxera.project.io import load_project_schema


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
    structured_plan: Optional[AgentPlan] = None
    structured_diff: Optional[AgentProjectDiff] = None
    structured_manifest: Optional[RunManifest] = None
    session_log: Optional[AgentSessionLog] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["actions"] = [asdict(a) for a in self.actions]
        return d


class AgentRuntime:
    def __init__(self, tools: Optional[AgentTools] = None, registry: Optional[AgentToolRegistry] = None):
        self.tools = tools or AgentTools()
        self.registry = registry or build_default_registry(self.tools)
        self._tool_call_depth = 0

    def _tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        self._tool_call_depth += 1
        try:
            return self.registry.call(tool_name, *args, **kwargs)
        finally:
            self._tool_call_depth -= 1

    def _deterministic_id(self, project_name: str, intent: str) -> str:
        h = hashlib.sha256(f"{project_name}\n{intent.strip().lower()}".encode("utf-8")).hexdigest()
        return h[:16]

    def execute(
        self,
        project_path: str,
        intent: str,
        approvals: Optional[Dict[str, Any]] = None,
    ) -> RuntimeResponse:
        approvals = approvals or {}
        project, ppath = self._tool("project.open", project_path)
        memory: Dict[str, Any] = {}
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
        selected_diff_ops = approvals.get("selected_diff_ops")
        selected_diff_ops_set = set(selected_diff_ops) if isinstance(selected_diff_ops, list) else None
        summary_ctx = self._tool("project.summarize", project)
        if getattr(summary_ctx, "ok", False):
            run_manifest["project_context"] = summary_ctx.data.get("summary", {})

        if "import" in lintent and "detect" in lintent and "grid" in lintent:
            file_path = self._extract_import_path(intent)
            if file_path is None:
                warnings.append("Import workflow requires a file path after 'import'.")
            else:
                ir = self._tool("geom.import", project, file_path=file_path)
                tool_calls.append({"tool": "import_geometry", "file_path": file_path, "workflow": "import_detect_grid"})
                if not ir.ok:
                    warnings.append(ir.message)
                cg = self._tool("geom.clean", project, detect_rooms=True)
                tool_calls.append({"tool": "clean_geometry", "detect_rooms": True, "workflow": "import_detect_grid"})
                if not cg.ok:
                    warnings.append(cg.message)
                room = project.geometry.rooms[0] if project.geometry.rooms else None
                width = room.width if room else 6.0
                height = room.length if room else 8.0
                nx = max(2, int(round(width / 0.25)) + 1)
                ny = max(2, int(round(height / 0.25)) + 1)
                gr = self._tool("project.grid.add", project, name="Agent Grid", width=width, height=height, elevation=0.8, nx=nx, ny=ny)
                tool_calls.append({"tool": "add_grid", "name": "Agent Grid", "elevation": 0.8, "spacing": 0.25, "workflow": "import_detect_grid"})
                if not gr.ok:
                    warnings.append(gr.message)

        if "place" in lintent or "layout" in lintent or "target" in lintent or ("hit" in lintent and "lux" in lintent):
            target = memory.get("preferred_target_lux", 500.0)
            for tok in lintent.replace("/", " ").split():
                try:
                    target = float(tok)
                except ValueError:
                    continue
            memory["preferred_target_lux"] = target
            pr = self._tool("project.diff.propose_layout", project, target, constraints={"max_rows": 6, "max_cols": 6})
            tool_calls.append({"tool": "propose_layout_diff", "target_lux": target})
            diff = pr.data["diff"]
            diff_preview = self._diff_preview(diff)
            actions.append(RuntimeAction(kind="apply_diff", requires_approval=True, payload={"op_count": diff_preview.get("count", 0)}))
            if approvals.get("apply_diff", False):
                diff_to_apply = self._filtered_diff(diff, selected_diff_ops_set)
                r = self._tool("project.diff.apply", project, diff_to_apply, approved=True)
                tool_calls.append({"tool": "apply_diff", "approved": True, "selected_ops": len(diff_to_apply.ops)})
                if not r.ok:
                    warnings.append(r.message)

        if "import" in lintent:
            # command style: /import <path>
            tokens = intent.strip().split()
            if len(tokens) >= 2:
                file_path = tokens[1]
                ir = self._tool("geom.import", project, file_path=file_path)
                tool_calls.append({"tool": "import_geometry", "file_path": file_path})
                if not ir.ok:
                    warnings.append(ir.message)
            else:
                warnings.append("Import intent requires file path.")

        if "detect rooms" in lintent or "clean geometry" in lintent:
            cg = self._tool("geom.clean", project, detect_rooms=True)
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
            gr = self._tool("project.grid.add", project, name="Agent Grid", width=width, height=height, elevation=elevation, nx=nx, ny=ny)
            tool_calls.append({"tool": "add_grid", "name": "Agent Grid", "elevation": elevation, "spacing": spacing, "nx": nx, "ny": ny})
            if not gr.ok:
                warnings.append(gr.message)

        if "optimizer" in lintent or "optimize" in lintent:
            job_id = project.jobs[0].id if project.jobs else ""
            if not job_id:
                warnings.append("Optimizer requested but project has no jobs.")
            else:
                constraints = {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0}
                orr = self._tool("optim.search", project, job_id=job_id, constraints=constraints, max_rows=4, max_cols=4, top_n=8)
                tool_calls.append({"tool": "optim.search", "job_id": job_id, "constraints": constraints})
                if orr.ok:
                    diff = orr.data["diff"]
                    diff_preview = self._diff_preview(diff)
                    run_manifest["optimizer"] = {
                        "best": orr.data.get("best"),
                        "top": orr.data.get("top"),
                        "artifact_json": orr.data.get("artifact_json"),
                    }
                    actions.append(RuntimeAction(kind="apply_diff", requires_approval=True, payload={"op_count": diff_preview.get("count", 0), "mode": "optimizer"}))
                    if approvals.get("apply_diff", False):
                        diff_to_apply = self._filtered_diff(diff, selected_diff_ops_set)
                        ar = self._tool("project.diff.apply", project, diff_to_apply, approved=True)
                        tool_calls.append({"tool": "apply_diff", "approved": True, "mode": "optimizer", "selected_ops": len(diff_to_apply.ops)})
                        if not ar.ok:
                            warnings.append(ar.message)
                else:
                    warnings.append(orr.message)

        if "design solve" in lintent or ("hit" in lintent and "lux" in lintent):
            job_id = project.jobs[0].id if project.jobs else ""
            if not job_id:
                warnings.append("Design solve requested but project has no jobs.")
            else:
                constraints = self._extract_design_constraints(intent)
                opt = self._tool("propose_optimizations", project, job_id=job_id, constraints=constraints, top_n=5)
                tool_calls.append({"tool": "propose_optimizations", "job_id": job_id, "constraints": constraints})
                if not opt.ok:
                    warnings.append(opt.message)
                else:
                    options = list(opt.data.get("options") or [])
                    selected_idx = int(approvals.get("selected_option_index", 0) or 0)
                    if selected_idx < 0:
                        selected_idx = 0
                    if options:
                        selected_idx = min(selected_idx, len(options) - 1)
                    run_manifest["design_solve"] = {
                        "job_id": job_id,
                        "constraints": constraints,
                        "options": options,
                        "selected_option_index": selected_idx,
                    }
                    actions.append(RuntimeAction(kind="review_options", requires_approval=True, payload={"count": len(options)}))
                    if approvals.get("apply_diff", False):
                        selected_option = options[selected_idx] if options else {}
                        od = self._tool("optim.option_diff", project, option=selected_option)
                        tool_calls.append({"tool": "optim.option_diff", "selected_option_index": selected_idx, "mode": "design_solve"})
                        if od.ok:
                            diff = od.data["diff"]
                            diff_preview = self._diff_preview(diff)
                            pcount = int(diff_preview.get("count", 0))
                            actions.append(RuntimeAction(kind="apply_diff", requires_approval=True, payload={"op_count": pcount, "mode": "design_solve"}))
                            diff_to_apply = self._filtered_diff(diff, selected_diff_ops_set)
                            ar = self._tool("project.diff.apply", project, diff_to_apply, approved=True)
                            tool_calls.append({"tool": "apply_diff", "approved": True, "mode": "design_solve", "selected_ops": len(diff_to_apply.ops)})
                            if not ar.ok:
                                warnings.append(ar.message)
                            else:
                                run_manifest["design_solve"]["applied_ops"] = len(diff_to_apply.ops)
                                run_manifest["design_solve"]["applied_option"] = selected_option
                        else:
                            warnings.append(od.message)
                    if approvals.get("run_job", False):
                        rr = self._tool("run_calc", project, job_id=job_id, approved=True)
                        tool_calls.append({"tool": "run_calc", "job_id": job_id, "approved": True, "mode": "design_solve"})
                        run_manifest["design_solve"]["run_result"] = rr.data
                        if rr.ok:
                            produced.append(rr.data.get("result_dir", ""))
                            project = load_project_schema(ppath)
                        else:
                            warnings.append(rr.message)

        if "try" in lintent and "option" in lintent:
            job_id = project.jobs[0].id if project.jobs else ""
            if not job_id:
                warnings.append("Optimizer requested but project has no jobs.")
            else:
                limit = 12
                for tok in lintent.replace(",", " ").split():
                    try:
                        v = int(tok)
                        if v > 0:
                            limit = v
                            break
                    except ValueError:
                        continue
                constraints = {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0}
                orr = self._tool("optim.optimizer", project, job_id=job_id, candidate_limit=limit, constraints=constraints)
                tool_calls.append({"tool": "optim.optimizer", "job_id": job_id, "candidate_limit": limit, "constraints": constraints})
                if orr.ok:
                    run_manifest["optimizer"] = dict(orr.data)
                    produced.extend([str(v) for v in orr.data.values()])
                else:
                    warnings.append(orr.message)

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
                    rr = self._tool("job.run", project, job_id=job_id, approved=True)
                    tool_calls.append({"tool": "run_job", "job_id": job_id, "approved": True})
                    run_manifest["run_result"] = rr.data
                    if rr.ok:
                        produced.append(rr.data.get("result_dir", ""))
                        # Canonical run path persists to disk; reload for subsequent steps in this turn.
                        project = load_project_schema(ppath)
                    else:
                        warnings.append(rr.message)

        if "report" in lintent:
            if not project.results:
                warnings.append("Cannot export report: no job results available.")
            else:
                job_id = project.results[-1].job_id
                wants_client = "client" in lintent
                wants_audit = "audit" in lintent or "debug" in lintent
                wants_roadway = "roadway" in lintent
                if wants_roadway:
                    out_html = str(ppath.parent / f"{project.name}_{job_id}_roadway_report.html")
                    rc = self._tool("report.roadway.html", project, job_id, out_html)
                    tool_calls.append({"tool": "export_roadway_report", "job_id": job_id, "out": out_html})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)
                if wants_client:
                    out_zip = str(ppath.parent / f"{project.name}_client_bundle.zip")
                    rc = self._tool("bundle.client", project, job_id, out_zip)
                    tool_calls.append({"tool": "export_client_bundle", "job_id": job_id, "out": out_zip})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)
                if wants_audit:
                    out_zip = str(ppath.parent / f"{project.name}_debug_bundle.zip")
                    rc = self._tool("bundle.audit", project, job_id, out_zip)
                    tool_calls.append({"tool": "export_debug_bundle", "job_id": job_id, "out": out_zip})
                    if rc.ok:
                        produced.append(rc.data["path"])
                    else:
                        warnings.append(rc.message)
                if not wants_client and not wants_audit and not wants_roadway:
                    out_pdf = str(ppath.parent / f"{project.name}_{job_id}_en12464.pdf")
                    rc = self._tool("report.pdf", project, job_id=job_id, report_type="en12464", out_path=out_pdf)
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
                hm = self._tool("results.heatmap", project, job_id=job_id)
                tool_calls.append({"tool": "render_heatmap", "job_id": job_id})
                if hm.ok:
                    produced.extend(list((hm.data.get("artifacts") or {}).values()))
                else:
                    warnings.append(hm.message)

        if "summarize" in lintent or "summary" in lintent:
            if project.results:
                job_id = project.results[-1].job_id
                sm = self._tool("results.summarize", project, job_id=job_id)
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
        session_payload = {
            "runtime_id": runtime_id,
            "intent": intent,
            "approvals": approvals,
            "plan": plan,
            "diff_preview": diff_preview,
            "run_manifest": run_manifest,
            "tool_calls": tool_calls,
            "actions": [asdict(a) for a in actions],
            "warnings": warnings,
            "produced_artifacts": produced,
        }
        self._tool("session.save", project, runtime_id=runtime_id, payload=session_payload)
        self._tool("project.save", project, ppath)

        structured_plan = AgentPlan(steps=[s.strip() for s in plan.split(",") if s.strip()], status="needs_input" if actions else "ok")
        structured_diff = AgentProjectDiff(preview=diff_preview)
        structured_manifest = RunManifest(payload=run_manifest)
        session_log = AgentSessionLog(tool_calls=tool_calls, warnings=warnings)

        return RuntimeResponse(
            plan=plan,
            diff_preview=diff_preview,
            run_manifest=run_manifest,
            actions=actions,
            produced_artifacts=produced,
            warnings=warnings,
            compliance_claimed=compliance_claimed,
            structured_plan=structured_plan,
            structured_diff=structured_diff,
            structured_manifest=structured_manifest,
            session_log=session_log,
        )

    @staticmethod
    def _extract_design_constraints(intent: str) -> Dict[str, float]:
        txt = intent.lower()
        out: Dict[str, float] = {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0}
        tokens = txt.replace(",", " ").replace("<", " < ").replace(">", " > ").split()
        for i, tok in enumerate(tokens):
            if tok.endswith("lux"):
                num = tok[:-3]
                try:
                    out["target_lux"] = float(num)
                except ValueError:
                    pass
            elif tok == "lux" and i > 0:
                try:
                    out["target_lux"] = float(tokens[i - 1])
                except ValueError:
                    pass
            elif tok == "ugr" and i + 2 < len(tokens) and tokens[i + 1] in {"<", "<="}:
                try:
                    out["ugr_max"] = float(tokens[i + 2])
                except ValueError:
                    pass
            elif tok == "u0" and i + 2 < len(tokens) and tokens[i + 1] in {">", ">="}:
                try:
                    out["uniformity_min"] = float(tokens[i + 2])
                except ValueError:
                    pass
        return out

    @staticmethod
    def _diff_op_key(index: int, op: DiffOp) -> str:
        return f"{index}:{op.op}:{op.kind}:{op.id}"

    def _diff_preview(self, diff: ProjectDiff) -> Dict[str, Any]:
        def _payload_fields(payload: Any) -> List[str]:
            if isinstance(payload, dict):
                return sorted([str(k) for k in payload.keys()])
            if hasattr(payload, "__dict__"):
                return sorted([str(k) for k in vars(payload).keys()])
            return []

        def _payload_summary(payload: Any) -> str:
            fields = _payload_fields(payload)
            if not fields:
                return ""
            shown = fields[:5]
            text = ", ".join(shown)
            if len(fields) > len(shown):
                text += ", ..."
            return text

        ops = [
            {
                "key": self._diff_op_key(i, op),
                "index": i,
                "op": op.op,
                "kind": op.kind,
                "id": op.id,
                "payload_fields": _payload_fields(op.payload),
                "payload_summary": _payload_summary(op.payload),
            }
            for i, op in enumerate(diff.ops)
        ]
        return {"ops": ops, "count": len(ops)}

    def _filtered_diff(self, diff: ProjectDiff, selected_op_keys: Optional[set[str]]) -> ProjectDiff:
        if selected_op_keys is None:
            return diff
        ops = [op for i, op in enumerate(diff.ops) if self._diff_op_key(i, op) in selected_op_keys]
        return ProjectDiff(ops=ops)

    @staticmethod
    def _extract_import_path(intent: str) -> Optional[str]:
        tokens = intent.strip().split()
        for i, t in enumerate(tokens):
            if t.lower() == "import" and i + 1 < len(tokens):
                return tokens[i + 1]
        return None
