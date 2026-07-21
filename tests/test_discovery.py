"""Tests for ``core.discovery`` — content-hash-based self-copy detection.

These tests validate that ``discover_files_txt`` correctly skips
auto-generated self-copies (the input file that ``_process_one``
copies into each arena folder) in Phase 2 of discovery.
"""
from __future__ import annotations

from pathlib import Path

from core.discovery import discover_files_txt


class TestSkipSelfCopies:
    """Validates the Phase 2 self-copy skip in ``discover_files_txt``."""

    def test_self_copy_in_arena_skipped(self, tmp_path: Path) -> None:
        """When an arena dir contains a copy of CWD's files.txt (same
        content), only the CWD source should be discovered. The
        self-copy in the arena folder is detected via SHA-256 content
        hash match and skipped.
        """
        cwd = tmp_path
        root = tmp_path
        # CWD source — the "real" input.
        (cwd / "files.txt").write_text("C:/some/file.py\n", encoding="utf-8")
        # Arena with self-copy (same content as CWD's files.txt).
        arena_dir = cwd / "context_output" / "arenas" / "001-files"
        arena_dir.mkdir(parents=True)
        (arena_dir / "001-files.txt").write_text("C:/some/file.py\n", encoding="utf-8")

        results = discover_files_txt(cwd, root, {"output_dir": "context_output"})

        # Only the CWD source should be discovered.
        assert len(results) == 1
        assert results[0][0].name == "files.txt"

    def test_real_input_in_arena_not_skipped(self, tmp_path: Path) -> None:
        """When an arena dir contains a DIFFERENT file from CWD's
        files.txt (different content), both should be discovered —
        the arena input is a real user-placed source, not a self-copy.
        Validates the false-positive guard.
        """
        cwd = tmp_path
        root = tmp_path
        (cwd / "files.txt").write_text("C:/cwd-source.py\n", encoding="utf-8")
        arena_dir = cwd / "context_output" / "arenas" / "001-foo"
        arena_dir.mkdir(parents=True)
        # Different content — this is a real input, not a self-copy.
        (arena_dir / "001-foo.txt").write_text("C:/arena-source.py\n", encoding="utf-8")

        results = discover_files_txt(cwd, root, {"output_dir": "context_output"})

        assert len(results) == 2
        names = {p.name for p, _ in results}
        assert names == {"files.txt", "001-foo.txt"}

    def test_skip_disabled_via_setting(self, tmp_path: Path) -> None:
        """When ``skip_tier1_self_copies=False``, the self-copy is NOT
        skipped — restores the pre-fix behavior of treating every
        ``NNN-name/NNN-name.txt`` in arena folders as a fresh input.
        """
        cwd = tmp_path
        root = tmp_path
        (cwd / "files.txt").write_text("C:/some/file.py\n", encoding="utf-8")
        arena_dir = cwd / "context_output" / "arenas" / "001-files"
        arena_dir.mkdir(parents=True)
        (arena_dir / "001-files.txt").write_text("C:/some/file.py\n", encoding="utf-8")

        results = discover_files_txt(
            cwd,
            root,
            {"output_dir": "context_output", "skip_tier1_self_copies": False},
        )

        # Both should be discovered when the skip is disabled.
        assert len(results) == 2
