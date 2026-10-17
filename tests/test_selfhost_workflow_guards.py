"""Keep upstream-only publishing jobs inactive in selfhost repositories."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    ("workflow", "job_name"),
    [
        ("publish-official-media-catalog.yml", "publish"),
        ("sync-to-gitee.yml", "sync"),
    ],
)
def test_upstream_publishing_jobs_require_exact_upstream_repository(workflow, job_name):
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / ".github" / "workflows" / workflow).read_text())

    assert set(data["jobs"]) == {job_name}
    job = data["jobs"][job_name]
    assert job["if"] == "${{ github.repository == 'dramaclaw/dramaclaw' }}"
    assert job["steps"], "Keep the upstream implementation behind the guard."
