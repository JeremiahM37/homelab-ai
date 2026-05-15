"""Release workflow YAML — has the jobs we expect."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent


def test_release_workflow_exists():
    assert (ROOT / ".github" / "workflows" / "release.yml").is_file()


def test_release_workflow_has_pypi_and_docker_jobs():
    with (ROOT / ".github" / "workflows" / "release.yml").open() as f:
        data = yaml.safe_load(f)
    jobs = data["jobs"]
    assert "pypi" in jobs
    assert "docker" in jobs
    assert "github-release" in jobs


def test_release_workflow_triggers_on_version_tag():
    with (ROOT / ".github" / "workflows" / "release.yml").open() as f:
        data = yaml.safe_load(f)
    # PyYAML parses "on" as the python boolean True — handle both shapes.
    triggers = data.get("on") if "on" in data else data.get(True)
    assert triggers is not None, "workflow must have an 'on' section"
    push = triggers.get("push", {})
    assert "v*.*.*" in push.get("tags", [])


def test_release_workflow_grants_required_permissions():
    with (ROOT / ".github" / "workflows" / "release.yml").open() as f:
        data = yaml.safe_load(f)
    perms = data.get("permissions", {})
    assert perms.get("packages") == "write", "need packages:write to push to GHCR"
    assert perms.get("id-token") == "write", "need id-token:write for PyPI trusted publishing"
