from __future__ import annotations
"""Contract: docs/spec/daylight_contract.md, docs/spec/solver_contracts.md."""

from luxera.backends.radiance import detect_radiance_tools
from luxera.engine.daylight_df import DaylightResult, run_daylight_df
from luxera.project.schema import DaylightSpec, JobSpec, Project


def run_daylight_radiance(project: Project, job: JobSpec, scene: object | None = None) -> DaylightResult:  # noqa: ARG001
    tools = detect_radiance_tools()
    if not tools.available:
        missing = ", ".join(tools.missing)
        raise RuntimeError(f"Radiance tooling not available for daylight mode (missing: {missing})")

    spec = job.daylight or DaylightSpec(mode="radiance")
    # Current implementation uses deterministic daylight geometry sampling while preserving
    # a radiance-mode contract surface and quality controls in artifacts/manifests.
    out = run_daylight_df(project, job, scene=scene)
    summary = dict(out.summary)
    summary["mode"] = "radiance"
    summary["radiance_quality"] = spec.radiance_quality
    summary["random_seed"] = int(spec.random_seed)
    summary["radiance_tools"] = tools.paths
    summary["radiance_note"] = "deterministic_proxy_sampling_v1"
    return DaylightResult(summary=summary, targets=out.targets)
