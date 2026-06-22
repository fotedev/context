"""Token counting utilities using tiktoken or a heuristic fallback."""

from typing import Protocol, cast


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
