"""Shared pytest fixtures."""
from pathlib import Path

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path):
    """Minimal config pointed at tmp directories."""
    from homelab_ai.config import Config
    cfg = Config()
    cfg.agent.enabled = False
    cfg.agent.fixer.backup_dir = str(tmp_path / "backups")
    cfg.agent.fixer.audit_log = str(tmp_path / "audit.md")
    cfg.settings.store_path = str(tmp_path / "settings.yaml")
    cfg.verify.fix_request_path = str(tmp_path / "fix-request.md")
    return cfg


class FakeResponse:
    def __init__(self, status=200, json_data=None, text_data="", headers=None,
                 content_length=None):
        self.status = status
        self._json = json_data
        self._text = text_data
        self.headers = headers or {}
        # Make sure content_length is truthy when json_data is provided so
        # plugins that gate on `r.content_length` don't short-circuit to {}.
        if content_length is not None:
            self.content_length = content_length
        elif text_data:
            self.content_length = len(text_data)
        elif json_data is not None:
            self.content_length = 1
        else:
            self.content_length = 0
        self.cookies = {}

    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def json(self): return self._json or {}
    async def text(self): return self._text
    def raise_for_status(self):
        if self.status >= 400:
            # Use a plain exception — aiohttp.ClientResponseError needs a
            # real RequestInfo for str() not to blow up.
            raise RuntimeError(f"HTTP {self.status}: {self._text or 'error'}")


class FakeSession:
    """Mimics enough of aiohttp.ClientSession for service plugins."""
    def __init__(self):
        self.handlers = {}  # (method, path_suffix) -> FakeResponse | callable

    def stub(self, method: str, suffix: str, response: FakeResponse):
        self.handlers[(method.upper(), suffix)] = response

    def _find(self, method: str, url: str):
        for (m, suf), resp in self.handlers.items():
            if m == method.upper() and url.endswith(suf):
                return resp
        return FakeResponse(status=404, text_data="not stubbed")

    def get(self, url, **_): return self._find("GET", url)
    def post(self, url, **_): return self._find("POST", url)
    def patch(self, url, **_): return self._find("PATCH", url)
    def put(self, url, **_): return self._find("PUT", url)
    def delete(self, url, **_): return self._find("DELETE", url)


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def FakeResponseFixture():
    return FakeResponse
