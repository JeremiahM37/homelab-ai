"""Verify framework — runner + fix-request handling."""

from homelab_ai.verify.runner import _CHECKS, check, run_all


def test_check_registration():
    """Reading the module registers the builtin checks."""
    import homelab_ai.verify.builtin_checks  # noqa: F401
    assert any(c.name == "config_loads" for c in _CHECKS)
    assert any(c.name == "fixer_caps_present" for c in _CHECKS)


def test_fix_request_written_on_failure(tmp_config, tmp_path, capsys):
    # Override CHECKS to one failing case for this test.
    from homelab_ai.verify import runner
    original = runner._CHECKS[:]
    runner._CHECKS.clear()

    @check(group="core", name="always_fails")
    def _fail(cfg):
        raise AssertionError("nope")

    rc = run_all(tmp_config)
    assert rc == 1
    fix_path = tmp_path / "fix-request.md"
    assert fix_path.is_file()
    assert "always_fails" in fix_path.read_text()

    runner._CHECKS[:] = original


def test_fix_request_deleted_on_success(tmp_config, tmp_path):
    """If a previous run wrote fix-request.md, a now-passing run should clear it."""
    fix_path = tmp_path / "fix-request.md"
    fix_path.write_text("# stale")

    from homelab_ai.verify import runner
    original = runner._CHECKS[:]
    runner._CHECKS.clear()

    @check(group="core", name="always_passes")
    def _pass(cfg):
        return None

    rc = run_all(tmp_config)
    assert rc == 0
    assert not fix_path.exists()

    runner._CHECKS[:] = original
