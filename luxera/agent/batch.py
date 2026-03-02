from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from luxera.agent.runtime import AgentRuntime


@dataclass(frozen=True)
class BatchStep:
    intent: str
    approve_all: bool = True
    fail_on_error: bool = True
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class BatchStepResult:
    step_index: int
    intent: str
    success: bool
    error: Optional[str]
    duration_seconds: float
    artifacts: List[str]


class BatchRunner:
    """
    Execute a sequence of agent intents against a project without
    interactive prompts. For CI/CD and automation.
    """

    def __init__(self, project_path: str, output_dir: Path):
        self.project_path = str(project_path)
        self.output_dir = Path(output_dir).expanduser().resolve()

    def run_steps(self, steps: List[BatchStep]) -> List[BatchStepResult]:
        """
        Execute each step sequentially.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        runtime = AgentRuntime()
        results: List[BatchStepResult] = []

        for idx, step in enumerate(steps):
            t0 = time.perf_counter()
            success = False
            error: Optional[str] = None
            artifacts: List[str] = []

            approvals = {"apply_diff": True, "run_job": True} if step.approve_all else {}
            try:
                rr = runtime.execute(self.project_path, step.intent, approvals=approvals)
                duration = time.perf_counter() - t0

                artifacts = [str(p) for p in (rr.produced_artifacts or []) if str(p)]
                # Also collect obvious artifact fields from manifest.
                manifest = rr.run_manifest if isinstance(rr.run_manifest, dict) else {}
                for key in ("result_dir", "report", "report_path", "artifact", "artifact_json"):
                    v = manifest.get(key)
                    if isinstance(v, str) and v:
                        artifacts.append(v)

                if duration > float(step.timeout_seconds):
                    success = False
                    error = f"step exceeded timeout ({duration:.2f}s > {step.timeout_seconds:.2f}s)"
                elif rr.warnings:
                    success = False
                    error = "; ".join(str(w) for w in rr.warnings)
                else:
                    success = True
            except Exception as e:
                duration = time.perf_counter() - t0
                success = False
                error = str(e)

            res = BatchStepResult(
                step_index=idx,
                intent=step.intent,
                success=success,
                error=error,
                duration_seconds=float(duration),
                artifacts=sorted(set(artifacts)),
            )
            results.append(res)

            if not res.success and step.fail_on_error:
                break

        return results

    def run_from_file(self, batch_file: Path) -> List[BatchStepResult]:
        """
        Load batch steps from a YAML or JSON file.
        """
        cfg = self._load_batch_file(batch_file)
        if not isinstance(cfg, dict):
            raise ValueError("Batch file must define an object at root")

        project_from_file = cfg.get("project")
        if project_from_file:
            self.project_path = str(project_from_file)
        output_from_file = cfg.get("output")
        if output_from_file:
            self.output_dir = Path(str(output_from_file)).expanduser().resolve()

        raw_steps = cfg.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Batch file requires non-empty 'steps' list")

        steps: List[BatchStep] = []
        for row in raw_steps:
            if isinstance(row, str):
                steps.append(BatchStep(intent=row))
                continue
            if isinstance(row, dict):
                intent = str(row.get("intent") or "").strip()
                if not intent:
                    continue
                steps.append(
                    BatchStep(
                        intent=intent,
                        approve_all=bool(row.get("approve_all", True)),
                        fail_on_error=bool(row.get("fail_on_error", True)),
                        timeout_seconds=float(row.get("timeout_seconds", 300.0)),
                    )
                )
        if not steps:
            raise ValueError("No valid steps found in batch file")
        return self.run_steps(steps)

    def generate_summary(self, results: List[BatchStepResult]) -> str:
        """
        Generate a summary report.
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed
        duration = sum(float(r.duration_seconds) for r in results)
        artifacts: List[str] = []
        for r in results:
            artifacts.extend([str(a) for a in r.artifacts if str(a)])
        artifacts = sorted(set(artifacts))

        lines = [
            f"Total steps: {total}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Total duration: {duration:.2f} seconds",
            f"Artifacts generated: {artifacts}",
        ]
        return "\n".join(lines)

    def _load_batch_file(self, batch_file: Path) -> Dict[str, Any]:
        p = Path(batch_file).expanduser().resolve()
        text = p.read_text(encoding="utf-8")
        suffix = p.suffix.lower()
        if suffix in {".json", ".js"}:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("Batch JSON root must be an object")
            return payload
        if suffix in {".yaml", ".yml"}:
            return self._parse_min_yaml(text)
        # fallback: try JSON first, then YAML-ish.
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return self._parse_min_yaml(text)

    @staticmethod
    def _parse_min_yaml(text: str) -> Dict[str, Any]:
        """Very small YAML subset parser for batch files (root keys + steps list)."""
        project = ""
        output = ""
        steps: List[Dict[str, Any]] = []
        in_steps = False
        current: Optional[Dict[str, Any]] = None

        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("project:"):
                project = line.split(":", 1)[1].strip().strip('"').strip("'")
                in_steps = False
                continue
            if line.startswith("output:"):
                output = line.split(":", 1)[1].strip().strip('"').strip("'")
                in_steps = False
                continue
            if line.startswith("steps:"):
                in_steps = True
                current = None
                continue
            if in_steps and line.startswith("- "):
                body = line[2:].strip()
                if body.startswith("intent:"):
                    intent = body.split(":", 1)[1].strip().strip('"').strip("'")
                    current = {"intent": intent}
                    steps.append(current)
                else:
                    current = {"intent": body.strip('"').strip("'")}
                    steps.append(current)
                continue
            if in_steps and current is not None and ":" in line:
                k, v = line.split(":", 1)
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                if key in {"approve_all", "fail_on_error"}:
                    current[key] = val.lower() in {"1", "true", "yes", "on"}
                elif key == "timeout_seconds":
                    try:
                        current[key] = float(val)
                    except ValueError:
                        current[key] = 300.0
                else:
                    current[key] = val

        return {"project": project, "output": output, "steps": steps}
