from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/server-compat.yml").read_text()
JOBS = yaml.safe_load(WORKFLOW)["jobs"]
CANONICAL_SCHEDULE_GUARD = (
    "github.event_name != 'schedule' || github.repository == 'omnigent-ai/omnigent'"
)


def test_scheduled_sweep_only_runs_in_canonical_repository() -> None:
    # Every job either is a root or needs one, so guarding the roots skips the
    # whole scheduled run in forks while keeping PR smoke and dispatch.
    roots = [name for name, job in JOBS.items() if "needs" not in job]
    assert sorted(roots) == ["resolve-latest", "setup", "setup-ui"]
    for name in roots:
        assert CANONICAL_SCHEDULE_GUARD in JOBS[name]["if"]


def test_no_job_bypasses_a_skipped_root() -> None:
    for job in JOBS.values():
        assert "always()" not in str(job.get("if", ""))
