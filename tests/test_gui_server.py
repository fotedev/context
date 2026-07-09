"""Integration tests for the FastAPI server (:mod:`gui.server.main`).

These boot the real app via ``fastapi.testclient.TestClient`` (which honours
the loopback middleware) and exercise every public endpoint. The shape of
each response is asserted against the TypeScript mirrors in
``gui/browser-extension/src/shared/types.ts``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# /health  (public — no auth)
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_expected_shape(self, fastapi_client) -> None:
        response = fastapi_client.get("/health")
        assert response.status_code == 200
        body = response.json()
        # Mirrors HealthStatus in shared/types.ts.
        assert set(body.keys()) == {"version", "project_root", "has_gemini_key", "pid"}
        assert isinstance(body["version"], str)
        assert isinstance(body["project_root"], str)
        assert isinstance(body["has_gemini_key"], bool)
        assert isinstance(body["pid"], int)


# ---------------------------------------------------------------------------
# /auth/pair + authenticated routes
# ---------------------------------------------------------------------------


class TestAuth:
    def test_pair_with_missing_code_400(self, fastapi_client) -> None:
        response = fastapi_client.post("/auth/pair", json={})
        assert response.status_code == 400
        assert "Pairing code" in response.json()["detail"]

    def test_pair_with_invalid_code_400(self, fastapi_client) -> None:
        response = fastapi_client.post("/auth/pair", json={"code": "nope"})
        assert response.status_code == 400

    def test_unauthenticated_settings_401(self, fastapi_client) -> None:
        response = fastapi_client.get("/api/settings")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# /api/settings  (wrapper shape — gap 5)
# ---------------------------------------------------------------------------


class TestSettingsEndpoint:
    def test_get_returns_wrapper_shape(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.get("/api/settings", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        # CRITICAL: wrapper shape, not flat dict.
        assert set(body.keys()) == {"settings", "message"}
        assert isinstance(body["settings"], dict)
        # All DEFAULT_SETTINGS keys present.
        assert "output_dir" in body["settings"]
        assert "model_count" in body["settings"]

    def test_put_updates_and_returns_wrapper(self, fastapi_client, auth_headers) -> None:
        payload = {"output_format": "txt", "model_count": 4}
        response = fastapi_client.put("/api/settings", json=payload, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["settings"]["output_format"] == "txt"
        assert body["settings"]["model_count"] == 4

    def test_put_partial_update_preserves_other_keys(
        self, fastapi_client, auth_headers
    ) -> None:
        # First GET to seed the file.
        fastapi_client.get("/api/settings", headers=auth_headers)
        # Now update one key.
        response = fastapi_client.put(
            "/api/settings", json={"compact_mode": True}, headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["settings"]["compact_mode"] is True
        # Other defaults remain.
        assert body["settings"]["model_count"] == 2


# ---------------------------------------------------------------------------
# /api/inputs  (wrapper shape — gap 6 / edge 9)
# ---------------------------------------------------------------------------


class TestInputsEndpoint:
    def test_empty_inputs_returns_wrapper_with_message(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.get("/api/inputs", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        # CRITICAL: wrapper, not bare list.
        assert set(body.keys()) == {"items", "message"}
        assert body["items"] == []
        assert "No input files found" in body["message"]

    def test_post_creates_input(self, fastapi_client, auth_headers) -> None:
        payload = {"name": "demo", "content": "hello world"}
        response = fastapi_client.post("/api/inputs", json=payload, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "path" in body
        assert body["name"] == "demo"

    def test_post_sanitises_name(self, fastapi_client, auth_headers) -> None:
        # Anything outside [A-Za-z0-9_-] is stripped.
        payload = {"name": "../evil name!", "content": "x"}
        response = fastapi_client.post("/api/inputs", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "evilname"

    def test_post_empty_name_400(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.post(
            "/api/inputs", json={"name": "@@@", "content": "x"}, headers=auth_headers
        )
        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]

    def test_list_after_create_returns_item(
        self, fastapi_client, auth_headers, tmp_project_root
    ) -> None:
        # Seed an inputs file.
        fastapi_client.post(
            "/api/inputs", json={"name": "zebra", "content": "z"}, headers=auth_headers
        )
        response = fastapi_client.get("/api/inputs", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        names = [it["name"] for it in body["items"]]
        assert "zebra" in names

    def test_delete_removes_input(self, fastapi_client, auth_headers) -> None:
        fastapi_client.post(
            "/api/inputs", json={"name": "doomed", "content": "x"}, headers=auth_headers
        )
        response = fastapi_client.delete(
            "/api/inputs/doomed", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_delete_missing_404(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.delete(
            "/api/inputs/ghost", headers=auth_headers
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/run/check  (gap 2 — edge 5 interactive merge/skip)
# ---------------------------------------------------------------------------


class TestRunCheckEndpoint:
    def test_no_conflict_for_fresh_arena(
        self, fastapi_client, auth_headers, sample_input_file
    ) -> None:
        response = fastapi_client.post(
            "/api/run/check",
            json={"input": "files"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        # Mirrors RunCheckResponse in shared/types.ts.
        assert set(body.keys()) == {"conflict", "existing_files"}
        assert body["conflict"] is False
        assert body["existing_files"] == []

    def test_detects_existing_arena(
        self, fastapi_client, auth_headers, sample_input_file, tmp_project_root
    ) -> None:
        # Pre-create the next arena folder so check reports a conflict.
        out_dir = tmp_project_root / "context_output"
        target = out_dir / "arenas" / "001-files"
        target.mkdir(parents=True, exist_ok=True)
        (target / "001-context.md").write_text("leftover", encoding="utf-8")

        response = fastapi_client.post(
            "/api/run/check",
            json={"input": "files"},
            headers=auth_headers,
        )
        body = response.json()
        assert body["conflict"] is True
        assert "001-context.md" in body["existing_files"]


# ---------------------------------------------------------------------------
# /api/run  (gap 3 — no-crash Gemini key contract)
# ---------------------------------------------------------------------------


class TestRunEndpoint:
    def test_run_returns_expected_shape(
        self, fastapi_client, auth_headers, sample_input_file, tmp_project_root
    ) -> None:
        response = fastapi_client.post(
            "/api/run",
            json={"input": "files", "overrides": {"model_count": 2}},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        # Mirrors RunResponse in shared/types.ts.
        assert set(body.keys()) == {"run_id", "arena_number", "arena_path", "warnings"}
        assert isinstance(body["run_id"], str)
        assert len(body["run_id"]) >= 8
        assert isinstance(body["arena_number"], int)
        assert body["arena_number"] >= 1
        assert isinstance(body["arena_path"], str)
        assert isinstance(body["warnings"], list)

    def test_run_creates_arena_directory(
        self, fastapi_client, auth_headers, sample_input_file, tmp_project_root
    ) -> None:
        body = fastapi_client.post(
            "/api/run", json={"input": "files"}, headers=auth_headers
        ).json()
        # The arena folder the API reported must exist on disk.
        assert Path(body["arena_path"]).is_dir()
        # And it lives under our (test) project root, not the real repo.
        arena_path = tmp_project_root / "context_output" / "arenas"
        assert any(arena_path.iterdir())  # at least one arena folder created

    def test_run_missing_input_404(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.post(
            "/api/run", json={"input": "ghost"}, headers=auth_headers
        )
        assert response.status_code == 404
        assert "Input file not found" in response.json()["detail"]

    def test_run_without_gemini_key_does_not_4xx(
        self, fastapi_client, auth_headers, sample_input_file, tmp_project_root, monkeypatch
    ) -> None:
        # Strip the env so gemini_judge=True silently degrades.
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_project_root)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        response = fastapi_client.post(
            "/api/run",
            json={
                "input": "files",
                "overrides": {"gemini_judge": True},
            },
            headers=auth_headers,
        )
        # No-crash contract: even with judge=True and no key, we get 200.
        assert response.status_code == 200
        warnings = response.json()["warnings"]
        assert any("GEMINI_API_KEY" in w for w in warnings)

    def test_run_overrides_apply_to_settings(
        self, fastapi_client, auth_headers, sample_input_file, tmp_project_root
    ) -> None:
        response = fastapi_client.post(
            "/api/run",
            json={
                "input": "files",
                "overrides": {"output_dir": "custom-output"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        # The custom output dir should have been created.
        assert (tmp_project_root / "custom-output" / "arenas").is_dir()

    def test_run_increments_arena_number(
        self, fastapi_client, auth_headers, sample_input_file
    ) -> None:
        first = fastapi_client.post(
            "/api/run", json={"input": "files"}, headers=auth_headers
        ).json()
        second = fastapi_client.post(
            "/api/run", json={"input": "files"}, headers=auth_headers
        ).json()
        assert second["arena_number"] > first["arena_number"]


# ---------------------------------------------------------------------------
# /api/ignore  (gap 1 — Req 9)
# ---------------------------------------------------------------------------


class TestIgnoreEndpoint:
    def test_get_returns_wrapper_shape(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.get("/api/ignore", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"patterns", "sources"}
        assert isinstance(body["patterns"], list)
        assert set(body["sources"].keys()) == {".context/ignore", ".contextignore"}

    def test_put_writes_only_context_ignore(
        self, fastapi_client, auth_headers, tmp_project_root
    ) -> None:
        # Pre-create a .contextignore file at the root — must NOT be touched.
        root_ignore = tmp_project_root / ".contextignore"
        root_ignore.write_text("# legacy\n", encoding="utf-8")

        response = fastapi_client.put(
            "/api/ignore",
            json={"patterns": ["foo", "bar"]},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # .context/ignore was written with the new patterns.
        ctx_ignore = tmp_project_root / ".context" / "ignore"
        assert "foo" in ctx_ignore.read_text(encoding="utf-8")
        # .contextignore is preserved verbatim.
        assert root_ignore.read_text(encoding="utf-8") == "# legacy\n"


# ---------------------------------------------------------------------------
# /api/env  (edge 6)
# ---------------------------------------------------------------------------


class TestEnvEndpoint:
    def test_update_env_persists_key(
        self, fastapi_client, auth_headers, tmp_project_root, monkeypatch
    ) -> None:
        # Redirect TOOL_ROOT so the .env is written inside tmp_project_root.
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_project_root)

        response = fastapi_client.post(
            "/api/env",
            json={"gemini_api_key": "sk-fake"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["has_gemini_key"] is True

        env_file = tmp_project_root / ".env"
        assert env_file.exists()
        assert "sk-fake" in env_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# /api/arenas + /api/arenas/{n}/{file}
# ---------------------------------------------------------------------------


class TestArenasEndpoint:
    def test_empty_returns_empty_list(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.get("/api/arenas", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_run_then_list_arenas(
        self, fastapi_client, auth_headers, sample_input_file
    ) -> None:
        # First run creates an arena folder.
        fastapi_client.post(
            "/api/run", json={"input": "files"}, headers=auth_headers
        )
        response = fastapi_client.get("/api/arenas", headers=auth_headers)
        arenas = response.json()
        assert len(arenas) == 1
        # Mirrors ArenaSummary in shared/types.ts.
        assert set(arenas[0].keys()) == {"number", "name", "files"}
        assert arenas[0]["name"] == "files"
        assert isinstance(arenas[0]["files"], list)

    def test_get_arena_file_returns_text(
        self, fastapi_client, auth_headers, sample_input_file
    ) -> None:
        fastapi_client.post(
            "/api/run", json={"input": "files"}, headers=auth_headers
        )
        # The run copies the input file into the arena dir as 001-files.txt.
        response = fastapi_client.get(
            "/api/arenas/1/001-files.txt", headers=auth_headers
        )
        assert response.status_code == 200
        assert "README.md" in response.text

    def test_get_arena_file_missing_404(
        self, fastapi_client, auth_headers
    ) -> None:
        response = fastapi_client.get(
            "/api/arenas/99/ghost.txt", headers=auth_headers
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/models + /api/models/{target}
# ---------------------------------------------------------------------------


class TestModelsEndpoint:
    def test_get_returns_expected_shape(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.get("/api/models", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        # Mirrors ModelFiles in shared/types.ts.
        assert set(body.keys()) == {"count", "files", "notes"}
        assert isinstance(body["count"], int)
        assert isinstance(body["files"], dict)
        assert isinstance(body["notes"], dict)

    def test_put_valid_target_writes_file(
        self, fastapi_client, auth_headers, tmp_project_root
    ) -> None:
        response = fastapi_client.put(
            "/api/models/A",
            json={"content": "Model A response"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["target"] == "A"
        # The file was actually written.
        path = tmp_project_root / "context_output" / "models" / "A.txt"
        assert path.read_text(encoding="utf-8") == "Model A response"

    def test_put_prompt_target_supported(
        self, fastapi_client, auth_headers
    ) -> None:
        # Req 5: prompt.txt is a first-class model-dir target.
        response = fastapi_client.put(
            "/api/models/prompt",
            json={"content": "the prompt"},
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_put_invalid_target_400(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.put(
            "/api/models/Z",
            json={"content": "x"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid model target" in response.json()["detail"]

    def test_put_model_count_4_auto_creates_empty_cd(
        self, fastapi_client, auth_headers, tmp_project_root
    ) -> None:
        # Configure model_count=4 then PUT A — C and D should be auto-created.
        fastapi_client.put(
            "/api/settings",
            json={"model_count": 4},
            headers=auth_headers,
        )
        fastapi_client.put(
            "/api/models/A",
            json={"content": "A content"},
            headers=auth_headers,
        )
        models_dir = tmp_project_root / "context_output" / "models"
        for letter in ("A", "B", "C", "D"):
            assert (models_dir / f"{letter}.txt").exists(), (
                f"{letter}.txt should be auto-created"
            )


# ---------------------------------------------------------------------------
# /project-root (auth)
# ---------------------------------------------------------------------------


class TestProjectRoot:
    def test_returns_root_path(self, fastapi_client, auth_headers) -> None:
        response = fastapi_client.get("/project-root", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert "root" in body
        assert isinstance(body["root"], str)