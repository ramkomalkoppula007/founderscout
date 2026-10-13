"""Shared test setup. pytest loads this file automatically.

Two promises to every test:
  1. it gets its own empty database and the fake model, so tests never touch
     your real data and never spend API quota;
  2. a small website is running on http://127.0.0.1:8765 for the browser.
"""
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):     # do not print every request
        pass


@pytest.fixture(scope="session")
def site():
    handler = functools.partial(QuietHandler, directory=str(FIXTURES / "site"))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    except OSError:              # you already have the test site running in a terminal
        yield "http://127.0.0.1:8765"
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:8765"
    server.shutdown()


@pytest.fixture(autouse=True)
def fresh_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("LLM_MODE", "fake")
    monkeypatch.setenv("ALLOW_PRIVATE_HOSTS", "true")
    monkeypatch.setenv("BROWSER_DELAY", "0")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("VIEWER_PASSWORD", "look")
    monkeypatch.setenv("FIT_THRESHOLD", "60")
    monkeypatch.setenv("MAX_REVISIONS", "2")

    from founderscout import config, db
    config.get_settings.cache_clear()      # settings are cached: read them again
    db.get_engine.cache_clear()
    db.init_db()
    yield
    db.get_engine().dispose()
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
