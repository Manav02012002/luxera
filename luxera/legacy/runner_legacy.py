from __future__ import annotations

"""Legacy runner namespace.

Legacy runner entrypoints were removed in favor of the project-schema runner
(`luxera.runner.run_job(project_path, job_id)`).
"""


class LegacyRunnerRemovedError(RuntimeError):
    pass


def run_job_legacy(*_args, **_kwargs):
    raise LegacyRunnerRemovedError(
        "Legacy runner path was removed. Use luxera.runner.run_job(project_path, job_id)."
    )
