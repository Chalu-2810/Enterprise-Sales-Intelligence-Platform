"""Centralized logging configuration for the platform."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "reports"
_LOG_FILE = _LOG_DIR / "app.log"
_MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3  # keep app.log.1 .. app.log.3


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance for the given module name.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A ``logging.Logger`` writing to both stdout and ``reports/app.log``.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured (avoid duplicate handlers on rerun)

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # If the filesystem is read-only in a deployment environment,
        # fall back silently to stream-only logging.
        pass

    return logger
