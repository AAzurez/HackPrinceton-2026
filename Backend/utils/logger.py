"""Logging utilities."""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "gridshift", level: str = "INFO") -> logging.Logger:
    """Create a console logger suitable for local demos."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
