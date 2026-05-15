# Contributing

Thanks for considering a contribution! homelab-ai is a small focused project — these guidelines keep it stay-able.

## Ground rules

- **Discuss first for non-trivial changes.** Open an issue before a large PR. Tiny fixes, typos, and obvious bugs are fine to send straight to a PR.
- **Generic over personal.** The project must be runnable by anyone — no hardcoded IPs, hostnames, API keys, paths, or assumptions about a specific stack. If you need a value, surface it through `config.yaml` or an environment variable.
- **Plugin > patch.** New services and tools should ship as plugins (see [docs/adding-services.md](docs/adding-services.md) and [docs/adding-tools.md](docs/adding-tools.md)), not by editing core code.
- **AI must not silently push to remotes.** The 3-tier fixer is allowed to edit local files, restart containers, and modify in-repo state. It is **not** allowed to `git push`, post to external services, or perform irreversible deletes without an explicit user-triggered action.

## Dev setup

```bash
git clone https://github.com/JeremiahM37/homelab-ai
cd homelab-ai
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # fill in your service URLs
homelab-ai run
```

Run the test suite:

```bash
pytest
python -m homelab_ai.verify           # functional / smoke tests against a live config
```

## Style

- `ruff check` for lint. `ruff format` for formatting. Both run in CI.
- Type hints on public functions. `mypy` is informational, not blocking.
- One module = one responsibility. Don't pile features into core; add a plugin.
- Tests should not require the maintainers' real homelab — mock external services or skip with a clear message.

## PR checklist

- [ ] `pytest` passes
- [ ] `ruff check` clean
- [ ] Updated docs if you changed behavior
- [ ] No secrets, IPs, or personal data leaked
- [ ] CHANGELOG entry under `## Unreleased`
