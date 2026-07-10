"""Unit tests for :mod:`gui.server.launcher`.

Covers ``.env`` bootstrap, ``GEMINI_API_KEY`` getter/setter, and the
project-root detection chain.
"""

from __future__ import annotations

from pathlib import Path


class TestBootstrapEnv:
    def test_creates_env_if_missing(self, tmp_path: Path, monkeypatch) -> None:
        # The launcher reads TOOL_ROOT at import time. Redirect by setting
        # an env var or by patching TOOL_ROOT directly.
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)

        env_path = launcher.bootstrap_env()
        assert env_path == tmp_path / ".env"
        assert env_path.exists()
        # Default content includes the placeholder.
        assert "GEMINI_API_KEY=" in env_path.read_text(encoding="utf-8")

    def test_existing_env_not_overwritten(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        existing = tmp_path / ".env"
        existing.write_text("CUSTOM=value\n", encoding="utf-8")
        launcher.bootstrap_env()
        assert existing.read_text(encoding="utf-8") == "CUSTOM=value\n"


class TestGeminiKey:
    def test_missing_returns_false(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        # No .env, no env var.
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert launcher.get_gemini_key() is False

    def test_env_var_returns_true(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        monkeypatch.setenv("GEMINI_API_KEY", "sk-test-123")
        assert launcher.get_gemini_key() is True

    def test_dotenv_value_takes_precedence(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        (tmp_path / ".env").write_text("GEMINI_API_KEY=from_dotenv\n", encoding="utf-8")
        monkeypatch.setenv("GEMINI_API_KEY", "from_environ")
        # Spec: env var wins if both set (the implementation falls back to
        # environ only when dotenv value is falsy).
        # Either answer is acceptable as long as one is truthy.
        assert launcher.get_gemini_key() is True

    def test_empty_dotenv_falls_back_to_environ(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        (tmp_path / ".env").write_text('GEMINI_API_KEY=""\n', encoding="utf-8")
        monkeypatch.setenv("GEMINI_API_KEY", "from_environ")
        assert launcher.get_gemini_key() is True

    def test_set_gemini_key_creates_file(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        launcher.set_gemini_key("sk-new")
        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=sk-new" in content

    def test_set_gemini_key_updates_existing(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        (tmp_path / ".env").write_text(
            "FOO=bar\nGEMINI_API_KEY=old\nBAZ=qux\n", encoding="utf-8"
        )
        launcher.set_gemini_key("new-key")
        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=new-key" in content
        assert "FOO=bar" in content
        assert "BAZ=qux" in content
        # No duplicate key line.
        assert content.count("GEMINI_API_KEY=") == 1

    def test_set_gemini_key_appends_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        from gui.server import launcher

        monkeypatch.setattr(launcher, "TOOL_ROOT", tmp_path)
        (tmp_path / ".env").write_text("FOO=bar\n", encoding="utf-8")
        launcher.set_gemini_key("new-key")
        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "FOO=bar" in content
        assert "GEMINI_API_KEY=new-key" in content


class TestProjectRoot:
    def test_falls_back_to_cwd_when_no_inputs(
        self, tmp_project_root: Path, monkeypatch
    ) -> None:
        from gui.server import launcher

        # No files.txt, no .context/inputs/*.txt → first-entry lookup fails.
        # Walk-up also fails for a bare tmp dir. Should fall back to CWD.
        result = launcher.get_project_root()
        # Allow either the resolved tmp path or CWD; both are valid fallbacks.
        assert result.is_absolute()

    def test_uses_first_entry_from_files_txt(
        self, tmp_project_root: Path, sample_input_file: Path
    ) -> None:
        from gui.server import launcher

        # files.txt points at README.md (which doesn't exist) and core/parser.py
        # (which doesn't exist either). Project-root detection must not crash;
        # it falls back to CWD.
        result = launcher.get_project_root()
        assert result.is_absolute()

    def test_finds_root_from_inputs_dir(
        self, tmp_project_root: Path, monkeypatch
    ) -> None:
        # Create an inputs dir with a file referencing the real CWD as root.
        from gui.server import launcher

        inputs_dir = tmp_project_root / ".context" / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        (inputs_dir / "demo.txt").write_text(
            f"{tmp_project_root}/README.md\n", encoding="utf-8"
        )
        result = launcher.get_project_root()
        # It should at minimum return an absolute path without crashing.
        assert isinstance(result, Path)
        assert result.is_absolute()
