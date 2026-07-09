"""Structured logging configuration for the context tool server.

Centralises the logging format and level so every backend module emits
events with the same shape — required for ops dashboards and unified log
search later on.

The format is deliberately compact and machine-parseable. Levels are
taken from the standard Python ``logging`` module and respect the
``GUI_SERVER_LOG_LEVEL`` environment variable (default ``"INFO"``).
Pipelines and WebSocket cycles show up with stable subsystem prefixes so
they can be filtered (``pipeline.*`` and ``ws.*``).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Final

#: Default log format. ``%(name)s`` carries the subsystem path so a single
#: grep can surface, e.g., all ``gui.server.pipeline`` events.
DEFAULT_FORMAT: Final[str] = (
    "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
)

#: Subsystems that we want to keep at INFO even when the global level is
#: set higher — these carry high-signal operational events.
_SUBSYSTEM_INFO_MIN: Final[tuple[str, ...]] = (
    "gui.server",
    "gui.server.ws",
    "gui.server.pipeline",
    "core.pipeline",
)


def configure_logging(level: str | None = None) -> None:
    """Idempotently configure root logging for the server.

    Idempotent so calling it twice (e.g. from the FastAPI factory AND the
    CLI ``--serve`` entrypoint) doesn't double-install handlers.

    Args:
        level: Optional override; defaults to ``GUI_SERVER_LOG_LEVEL``
            env var, then ``"INFO"``.
    """
    root = logging.getLogger()
    if getattr(root, "_gui_server_configured", False):
        return

    effective = (level or os.environ.get("GUI_SERVER_LOG_LEVEL") or "INFO").upper()
    root.setLevel(effective)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    root.addHandler(handler)

    # Subsystem floors — the named loggers should always emit INFO events
    # even when the root level is WARNING, so we never silently lose the
    # pipeline / WS connection cycles the ops dashboard depends on.
    for name in _SUBSYSTEM_INFO_MIN:
        lg = logging.getLogger(name)
        lg.setLevel(min(lg.level or logging.NOTSET, logging.INFO))

    root._gui_server_configured = True  # type: ignore[attr-defined]
    logger = logging.getLogger(__name__)
    logger.debug(
        "Server logging configured (level=%s, handler=stderr)", effective
    )
