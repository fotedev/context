"""Token counting utilities using tiktoken or a heuristic fallback."""

from typing import Protocol, cast
from pathlib import Path


class TiktokenEncoding(Protocol):
    def encode(self, text: str) -> list[int]:
        ...


def count_tokens(text: str) -> int:
    """Calculate or estimate the number of tokens in the given text.

    Attempts to use `tiktoken` (cl100k_base encoding) if installed.
    Otherwise, falls back to a standard estimation: max of characters / 4
    and words * 1.3.

    Args:
        text: The text content to analyze.

    Returns:
        The estimated or exact token count.
    """
    try:
        import tiktoken

        # Use cast and TiktokenEncoding protocol to avoid Type Any is not allowed.
        encoding = cast(TiktokenEncoding, tiktoken.get_encoding("cl100k_base"))
        return len(encoding.encode(text))
    except ImportError:
        char_count = len(text)
        word_count = len(text.split())

        char_estimate = char_count // 4
        word_estimate = int(word_count * 1.3)

        return max(char_estimate, word_estimate)


def count_lines(path: Path, ranges: list[tuple[int, int]] | None = None) -> int:
    """Count lines in a file, optionally limited to specific line ranges.

    Args:
        path: Path to the file.
        ranges: Optional list of (start, end) line ranges (1-indexed, inclusive).

    Returns:
        Number of lines (or lines in ranges).
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
            total = len(lines)
            if ranges is None:
                return total
            
            count = 0
            sorted_ranges = sorted(ranges, key=lambda r: r[0])
            for start, end in sorted_ranges:
                # Inverted range (start > end) — caller passed garbage;
                # treat as zero-line range instead of crashing.
                if end < start:
                    continue
                start_idx = max(0, start - 1)
                end_idx = min(total, end)
                if start_idx < end_idx:
                    count += end_idx - start_idx
            return count
    except (OSError, UnicodeDecodeError):
        return 0
