"""Shared pytest fixtures for the context-aggregator test suite.

Fixtures cover the four most common scenarios:

* :func:`tmp_project_root` — isolated project root with ``.context/`` set up.
* :func:`fake_settings` — a fresh :class:`core.settings.Settings` instance.
* :func:`fastapi_client` — a ``TestClient`` bound to a freshly-created app,
  with the loopback middleware satisfied (TestClient connects from 127.0.0.1).
* :func:`pairing_token` — exchanges a freshly-minted pairing code for a bearer
  token, ready to inject into authenticated requests.
* :func:`reset_security_state` — clears module-level in-memory stores in
  ``gui.server.security`` between tests to avoid cross-test pollution.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # noqa: TC002 — used in fixture return type

# Module-level imports for type annotations used in fixtures below.
# Even with `from __future__ import annotations`, @pytest.fixture inspects
# the return-type annotation at decoration time, so the names must be
# resolvable in the module scope.
from core.settings import Settings  # noqa: TC002 — used in fixture return type

# Make the project root importable so `core.*` and `gui.server.*` resolve the
# same way they do from a CLI run.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Pretend we're running from inside the tmp project root so launcher's
# `Path.cwd()` lookups resolve there.
os.environ.setdefault("PYTHONHASHSEED", "0")


@pytest.fixture
def fake_settings() -> "Settings":
    """Default :class:`core.settings.Settings` instance.

    Tests should derive modified copies via ``dataclasses.replace`` and
    attribute access; the original defaults are never mutated.
    """
    from core.settings import Settings

    return Settings()


@pytest.fixture
def tmp_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated project root and chdir into it for the test.

    The fixture:

    1. Creates ``tmp_path`` (pytest-managed, auto-cleaned).
    2. ``chdir``'s the process into it so ``Path.cwd()``-based helpers in
       :mod:`gui.server.launcher` resolve correctly.
    3. Creates ``.context/inputs/`` so input discovery doesn't crash.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".context" / "inputs").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def reset_security_state() -> Iterator[None]:
    """Clear pairing-code + token stores between tests.

    The security module uses module-level dicts (single-process server, so
    this is fine in production). Tests need a clean slate.
    """
    from gui.server import security

    security._pairing_codes.clear()
    security._valid_tokens.clear()
    yield
    security._pairing_codes.clear()
    security._valid_tokens.clear()


@pytest.fixture
def fastapi_client(
    tmp_project_root: Path,
    reset_security_state: None,
) -> Iterator["TestClient"]:
    """A ``TestClient`` bound to a fresh app instance.

    The TestClient connects from a local socket, so the loopback middleware
    is satisfied out of the box. Authenticated routes will still need a
    bearer token — see :func:`pairing_token`.
    """
    from fastapi.testclient import TestClient
    from gui.server import launcher, main as server_main

    # Force get_project_root() to return the test's tmp_path — otherwise the
    # real repo root is detected via walking up from CWD, and settings would
    # leak across tests (and pollute the real repo's .context/).
    # main.py imports `get_project_root` at module load, so we patch BOTH the
    # launcher export and the bound reference inside the server module.
    original_launcher_root = launcher.get_project_root
    original_main_root = server_main.get_project_root
    launcher.get_project_root = lambda: tmp_project_root
    server_main.get_project_root = lambda: tmp_project_root
    try:
        app = server_main.create_app()
        with TestClient(app) as client:
            yield client
    finally:
        launcher.get_project_root = original_launcher_root
        server_main.get_project_root = original_main_root


@pytest.fixture
def pairing_token(fastapi_client) -> str:
    """Mint a pairing code, exchange it for a bearer token, return the token.

    Public-only endpoint flow (no auth needed for /auth/pair). The token is
    ready to inject as ``Authorization: Bearer <token>``.
    """
    from gui.server.security import generate_pairing_code

    code = generate_pairing_code()
    response = fastapi_client.post("/auth/pair", json={"code": code})
    assert response.status_code == 200, response.text
    return response.json()["token"]


@pytest.fixture
def auth_headers(pairing_token: str) -> dict[str, str]:
    """Authorization headers dict for authenticated API calls."""
    return {"Authorization": f"Bearer {pairing_token}"}


@pytest.fixture
def sample_input_file(tmp_project_root: Path) -> Path:
    """Create a realistic ``files.txt`` with two entries — used by /api/run tests."""
    files_txt = tmp_project_root / "files.txt"
    files_txt.write_text(
        "README.md\n"
        "core/parser.py 10-30\n",
        encoding="utf-8",
    )
    return files_txt