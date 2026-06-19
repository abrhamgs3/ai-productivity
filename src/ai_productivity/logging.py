"""
Centralized logging for the AI and Productivity pipeline.

Usage
-----
    from ai_productivity.logging import get_logger

    log = get_logger(__name__)
    log.info("Loading World Bank data...")
    log.warning("3 unmatched ISO3 codes — check data/raw/wdi.csv")
    log.error("Merge failed: duplicate keys in pwt.csv")

Why structured logging?
-----------------------
``print()`` statements disappear in production runs and can't be filtered.
A proper logger lets you:
- Control verbosity with a single flag (--verbose / --quiet).
- Redirect output to a log file for reproducibility auditing.
- Silence third-party libraries independently of your own messages.
"""

import logging
import sys
from pathlib import Path

# Module-level cache so callers sharing the same __name__ get the same logger.
_loggers: dict[str, logging.Logger] = {}

_DEFAULT_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_SHORT_FORMAT = "%(levelname)-8s  %(message)s"


def get_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger for *name*.

    The first call for a given name creates and caches the logger; subsequent
    calls return the cached instance.  This matches the standard library
    ``logging.getLogger`` contract but adds our default formatting.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.
    level:
        Default log level.  Override per-module if needed.
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if the root logger is already configured
    # (e.g., when running inside pytest or Jupyter).
    if not logger.handlers and not logging.root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_SHORT_FORMAT))
        logger.addHandler(handler)
        logger.propagate = False

    _loggers[name] = logger
    return logger


def configure_logging(
    *,
    level: int = logging.INFO,
    log_file: Path | None = None,
    verbose: bool = False,
) -> None:
    """Global logging configuration.  Call once at application startup.

    Parameters
    ----------
    level:
        Root log level (e.g., ``logging.DEBUG``, ``logging.WARNING``).
    log_file:
        Optional path to write a persistent log.  The file is appended to, not
        overwritten, so each pipeline run accumulates history.
    verbose:
        If ``True``, forces ``DEBUG`` level regardless of *level*.
    """
    if verbose:
        level = logging.DEBUG

    fmt = logging.Formatter(_DEFAULT_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

    # Optional file handler
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Quieten noisy third-party loggers
    for noisy in ("matplotlib", "PIL", "urllib3", "httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
