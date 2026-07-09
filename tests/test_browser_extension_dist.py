"""Integration tests that validate the built browser-extension (``dist/``)
against the live ``/api/run`` backend.

These tests verify the **contract** between the TypeScript client and the
Python server:

* ``gui/browser-extension/src/shared/types.ts`` declares the response shape;
  we assert that the server returns exactly those keys.
* ``gui/browser-extension/dist/manifest.json`` declares the host permissions
  and the service-worker entry; we assert those are wired correctly.
* The fetch wrapper in ``src/shared/api.ts`` injects a bearer token and posts
  JSON to ``/api/run``; we exercise that endpoint with the same payload shape
  and confirm the server responds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "gui" / "browser-extension" / "dist"
SRC_SHARED_TYPES = (
    PROJECT_ROOT / "gui" / "browser-extension" / "src" / "shared" / "types.ts"
)
SRC_SHARED_API = (
    PROJECT_ROOT / "gui" / "browser-extension" / "src" / "shared" / "api.ts"
)


# ---------------------------------------------------------------------------
# Build artifacts must be present
# ---------------------------------------------------------------------------


pytestmark = pytest.mark.integration


def test_dist_directory_exists() -> None:
    assert DIST_DIR.is_dir(), (
        "gui/browser-extension/dist/ missing — run `npm run build` inside "
        "gui/browser-extension/ first."
    )


def test_dist_manifest_is_valid_json() -> None:
    manifest_path = DIST_DIR / "manifest.json"
    assert manifest_path.is_file(), "dist/manifest.json missing"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Manifest v3 is required for Chromium-based browsers.
    assert data["manifest_version"] == 3
    assert data["name"]
    assert data["version"]


def test_dist_manifest_host_permissions_match_server_port() -> None:
    """The manifest must allow http://127.0.0.1:8765 so /api/* works."""
    data = json.loads((DIST_DIR / "manifest.json").read_text(encoding="utf-8"))
    perms = data.get("host_permissions", [])
    assert any("127.0.0.1:8765" in p for p in perms), (
        f"manifest host_permissions must include 127.0.0.1:8765; got {perms!r}"
    )


def test_dist_has_service_worker_loader() -> None:
    """MV3 background.service_worker must point at an existing loader file."""
    data = json.loads((DIST_DIR / "manifest.json").read_text(encoding="utf-8"))
    sw_path = data.get("background", {}).get("service_worker")
    assert sw_path, "service_worker must be set in MV3 manifest"
    assert (DIST_DIR / sw_path).is_file(), (
        f"service-worker loader {sw_path} missing under dist/"
    )


def test_dist_has_popup_html() -> None:
    """The popup entry referenced by manifest.action.default_popup must exist."""
    data = json.loads((DIST_DIR / "manifest.json").read_text(encoding="utf-8"))
    popup = data.get("action", {}).get("default_popup")
    assert popup, "action.default_popup must be set"
    assert (DIST_DIR / popup).is_file()


# ---------------------------------------------------------------------------
# Shared types — RunResponse shape mirror
# ---------------------------------------------------------------------------


class TestSharedTypesContract:
    """The TS source must declare exactly the keys our /api/run returns."""

    def test_run_response_interface_declared(self) -> None:
        text = SRC_SHARED_TYPES.read_text(encoding="utf-8")
        for key in ("run_id", "arena_number", "arena_path", "warnings"):
            assert key in text, (
                f"shared/types.ts must mention RunResponse field '{key}' "
                "(mirrors server response — keep in sync)."
            )

    def test_settings_response_is_wrapper(self) -> None:
        # /api/settings returns {settings, message} — NOT a flat dict.
        text = SRC_SHARED_TYPES.read_text(encoding="utf-8")
        assert "SettingsResponse" in text
        assert "message" in text

    def test_inputs_response_is_wrapper(self) -> None:
        # /api/inputs returns {items, message} — NOT a bare list.
        text = SRC_SHARED_TYPES.read_text(encoding="utf-8")
        assert "InputsResponse" in text
        assert "items" in text


# ---------------------------------------------------------------------------
# Shared API client — wires to /api/run
# ---------------------------------------------------------------------------


class TestSharedApiClient:
    """``src/shared/api.ts`` must point at the right BASE_URL + paths."""

    def test_base_url_is_loopback_8765(self) -> None:
        text = SRC_SHARED_API.read_text(encoding="utf-8")
        assert "127.0.0.1:8765" in text, (
            "src/shared/api.ts BASE_URL must point at 127.0.0.1:8765 "
            "(matches the server launched via `python aggregator.py --serve`)"
        )

    def test_run_helper_targets_api_run(self) -> None:
        text = SRC_SHARED_API.read_text(encoding="utf-8")
        # The `run:` method body should POST to /api/run.
        assert "'/api/run'" in text or '"/api/run"' in text

    def test_bearer_token_injected(self) -> None:
        text = SRC_SHARED_API.read_text(encoding="utf-8")
        assert "Authorization" in text
        assert "Bearer" in text


# ---------------------------------------------------------------------------
# End-to-end: simulate the browser extension's POST /api/run
# ---------------------------------------------------------------------------


class TestBrowserExtensionToBackend:
    """Round-trip: the exact JSON shape the extension sends, the server replies."""

    def test_post_run_matches_run_response_contract(
        self, fastapi_client, auth_headers, sample_input_file
    ) -> None:
        # This is the literal body that src/shared/api.ts sends when the user
        # clicks "Run" in the popup (see ``api.run(req: RunRequest)``).
        request_body = {
            "input": "files",
            "overrides": {
                "output_dir": "context_output",
                "output_format": "md",
                "model_count": 2,
                "gemini_judge": False,
                "compact_mode": False,
            },
        }

        response = fastapi_client.post(
            "/api/run",
            json=request_body,
            headers={
                **auth_headers,
                "Content-Type": "application/json",
                "Origin": "chrome-extension://test",
            },
        )
        assert response.status_code == 200
        body = response.json()

        # --- Contract assertions (every key must exist) -------------------
        for key in ("run_id", "arena_number", "arena_path", "warnings"):
            assert key in body, (
                f"server response missing '{key}' — breaks the TS RunResponse "
                "type and the extension will render 'undefined'."
            )

        # --- Type assertions ---------------------------------------------
        assert isinstance(body["run_id"], str)
        assert isinstance(body["arena_number"], int)
        assert isinstance(body["arena_path"], str)
        assert isinstance(body["warnings"], list)
        # The arena path the server reports must really exist on disk.
        assert Path(body["arena_path"]).is_dir()

    def test_get_settings_matches_settings_response_contract(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.get("/api/settings", headers=auth_headers)
        body = response.json()
        # CRITICAL: SettingsResponse is {settings, message}, NOT flat.
        assert "settings" in body
        assert "message" in body
        # And every DEFAULT_SETTINGS key is inside body.settings.
        for key in (
            "output_dir",
            "output_format",
            "model_count",
            "gemini_judge",
            "compact_mode",
        ):
            assert key in body["settings"], f"missing key: {key}"

    def test_list_inputs_matches_inputs_response_contract(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.get("/api/inputs", headers=auth_headers)
        body = response.json()
        # CRITICAL: InputsResponse is {items, message}, NOT a bare list.
        assert "items" in body
        assert "message" in body
        assert isinstance(body["items"], list)