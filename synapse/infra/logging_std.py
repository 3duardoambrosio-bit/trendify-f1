from __future__ import annotations

import logging
from typing import Any


_DEFAULT_FMT = "%(asctime)s %(levelname)s %(name)s | %(message)s"


def configure_logging(
    *,
    level: str = "INFO",
    fmt: str = _DEFAULT_FMT,
) -> None:
    """
    Idempotent-ish logging config.
    Important: importing this module does nothing. You must call configure_logging().
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured by app/test runner; keep hands off.
        return
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_kv(logger: logging.Logger, msg: str, **kv: Any) -> None:
    if not kv:
        logger.info(msg)
        return
    extra = " ".join([f"{k}={kv[k]!r}" for k in sorted(kv.keys())])
    logger.info("%s | %s", msg, extra)
