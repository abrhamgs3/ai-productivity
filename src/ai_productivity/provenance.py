"""
src/ai_productivity/provenance.py
===================================
Reproducibility metadata recorder for the AI & Productivity research pipeline.

Usage — context-manager (recommended)
--------------------------------------
Wrap any pipeline call without touching the pipeline itself::

    from ai_productivity.provenance import ProvenanceRecorder

    with ProvenanceRecorder(
        config_path="config/config.yaml",
        input_paths=["data/processed/panel_clean.csv"],
        output_dirs=["tables", "figures", "paper/sections"],
    ) as rec:
        run_pipeline()          # ← unchanged, unaware of the recorder

    # Metadata is written automatically on __exit__.
    # Default destination: outputs/provenance/run_metadata.json

Usage — functional
-------------------
::

    from ai_productivity.provenance import record_run

    record_run(
        run_pipeline,
        config_path="config/config.yaml",
        input_paths=["data/processed/panel_clean.csv"],
    )

Isolation guarantee
--------------------
The recorder never imports from, monkey-patches, or modifies any production
module.  It reads the filesystem *before* and *after* the pipeline call.  The
only side-effect is writing ``outputs/provenance/run_metadata.json``.

Schema
-------
See ``outputs/provenance/schema.json`` for the authoritative JSON Schema.
The top-level keys are:

``schema_version``
    Semver string for the metadata format.  Increment the minor version when
    new optional keys are added; increment the major version when existing
    keys are renamed or removed.  Current value: ``"1.0.0"``.

``run_id``
    UUID4 string.  Unique per execution — useful for correlating log lines
    with a specific metadata file when multiple runs are archived.

``timestamp_utc``
    ISO-8601 UTC start time (``YYYY-MM-DDTHH:MM:SS.ffffffZ``).

``runtime_seconds``
    Wall-clock duration of the wrapped callable.  ``null`` when the run
    failed before completion.

``exit_status``
    ``"success"`` or ``"error: <exception type>"``.

``git``
    ``commit``, ``branch``, ``dirty`` (bool — True if working tree has
    uncommitted changes), ``tags`` (list of tags pointing to this commit).

``python``
    ``version`` (e.g. ``"3.11.9"``), ``implementation`` (``"CPython"``).

``platform``
    ``system``, ``release``, ``machine``, ``node`` (hostname, anonymised to
    SHA-256 prefix so it is identifiable within a lab but not externally).

``packages``
    Dict mapping package name → installed version string for every package
    in ``TRACKED_PACKAGES``.  ``null`` when the package is not installed.

``config``
    ``path``, ``sha256``, ``content_preview`` (first 512 characters of the
    config file, for quick visual inspection without opening the file).
    ``null`` when no ``config_path`` was supplied.

``inputs``
    List of dicts, one per input path: ``path``, ``sha256``,
    ``size_bytes``, ``mtime_utc``.  Paths that do not exist at recording
    time are recorded with ``sha256: null`` and a ``warning`` field.

``outputs``
    List of dicts, one per output artifact discovered in ``output_dirs``
    after the pipeline completes: ``path``, ``sha256``, ``size_bytes``.
    Sorted by path for stable diffs.  Empty list when no ``output_dirs``
    are supplied or the directories do not exist.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as _meta
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: str = "1.0.0"

#: Packages whose versions are recorded unconditionally.
TRACKED_PACKAGES: tuple[str, ...] = (
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "linearmodels",
    "scikit-learn",
    "matplotlib",
    "seaborn",
    "pyyaml",
    "pyarrow",
    "openpyxl",
    "Pillow",
    "pytest",
)

DEFAULT_OUTPUT_PATH: Path = Path("outputs/provenance/run_metadata.json")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    """Return hex SHA-256 of *path*, or ``None`` if the file cannot be read."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65_536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _git_info(repo_root: Path | None) -> dict:
    """Collect git provenance.  Returns empty strings on failure (not a git repo)."""
    root = str(repo_root) if repo_root else "."

    def _run(*args: str) -> str:
        try:
            return subprocess.check_output(
                args, cwd=root, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    commit = _run("git", "rev-parse", "HEAD")
    branch = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    status = _run("git", "status", "--porcelain")
    tags   = _run("git", "tag", "--points-at", "HEAD")

    return {
        "commit": commit or None,
        "branch": branch or None,
        "dirty":  bool(status),
        "tags":   [t for t in tags.splitlines() if t] if tags else [],
    }


def _python_info() -> dict:
    v = sys.version_info
    return {
        "version":        f"{v.major}.{v.minor}.{v.micro}",
        "implementation": platform.python_implementation(),
        "executable":     sys.executable,
    }


def _platform_info() -> dict:
    node_raw  = platform.node()
    node_hash = hashlib.sha256(node_raw.encode()).hexdigest()[:12]
    return {
        "system":    platform.system(),
        "release":   platform.release(),
        "machine":   platform.machine(),
        "node_hash": node_hash,   # anonymised hostname prefix
    }


def _package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for pkg in TRACKED_PACKAGES:
        try:
            result[pkg] = _meta.version(pkg)
        except _meta.PackageNotFoundError:
            result[pkg] = None
    return result


def _config_info(config_path: str | Path | None) -> dict | None:
    if config_path is None:
        return None
    p = Path(config_path)
    sha = _sha256_file(p)
    preview: str | None = None
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
        preview = raw[:512]
    except OSError:
        pass
    return {
        "path":            str(p),
        "sha256":          sha,
        "content_preview": preview,
    }


def _input_records(input_paths: Iterable[str | Path]) -> list[dict]:
    records = []
    for raw in input_paths:
        p    = Path(raw)
        sha  = _sha256_file(p)
        stat = None
        try:
            stat = p.stat()
        except OSError:
            pass
        rec: dict = {"path": str(p)}
        if stat is not None:
            rec["sha256"]     = sha
            rec["size_bytes"] = stat.st_size
            rec["mtime_utc"]  = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()
        else:
            rec["sha256"]     = None
            rec["size_bytes"] = None
            rec["mtime_utc"]  = None
            rec["warning"]    = "path did not exist at record time"
        records.append(rec)
    return records


def _output_records(output_dirs: Iterable[str | Path]) -> list[dict]:
    records = []
    for raw in output_dirs:
        d = Path(raw)
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            records.append(
                {
                    "path":       str(p),
                    "sha256":     _sha256_file(p),
                    "size_bytes": stat.st_size,
                }
            )
    return sorted(records, key=lambda r: r["path"])


def _write_json(data: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(dest)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ProvenanceRecorder:
    """Context-manager that captures pipeline reproducibility metadata.

    Parameters
    ----------
    config_path:
        Path to the configuration file used by the pipeline.  Its SHA-256
        and first 512 characters are recorded.
    input_paths:
        Paths to input datasets (e.g. ``data/processed/panel_clean.csv``).
        SHA-256, size, and modification time are recorded *before* the run.
    output_dirs:
        Directories to scan for output artifacts *after* the run.  All
        files found recursively are recorded with their SHA-256 and size.
    output_path:
        Destination for the metadata JSON file.
        Default: ``outputs/provenance/run_metadata.json``.
    repo_root:
        Directory containing the ``.git`` folder.  Defaults to the current
        working directory.

    Example
    -------
    ::

        with ProvenanceRecorder(
            config_path="config/config.yaml",
            input_paths=["data/processed/panel_clean.csv"],
            output_dirs=["tables", "figures", "paper/sections"],
        ):
            run_pipeline()
    """

    def __init__(
        self,
        *,
        config_path:  str | Path | None        = None,
        input_paths:  Sequence[str | Path]     = (),
        output_dirs:  Sequence[str | Path]     = (),
        output_path:  str | Path               = DEFAULT_OUTPUT_PATH,
        repo_root:    str | Path | None        = None,
    ) -> None:
        self.config_path  = config_path
        self.input_paths  = list(input_paths)
        self.output_dirs  = list(output_dirs)
        self.output_path  = Path(output_path)
        self.repo_root    = Path(repo_root) if repo_root else None

        self._metadata:    dict | None = None
        self._start_time:  float       = 0.0
        self._run_id:      str         = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "ProvenanceRecorder":
        self._start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        exit_status = (
            "success" if exc_type is None
            else f"error: {exc_type.__name__}"
        )
        self._finish(exit_status=exit_status)
        # Never suppress exceptions from the pipeline
        return False

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        self._start_time = time.monotonic()
        self._metadata = {
            "schema_version":  SCHEMA_VERSION,
            "run_id":          self._run_id,
            "timestamp_utc":   datetime.now(tz=timezone.utc).isoformat(),
            "runtime_seconds": None,
            "exit_status":     "unknown",
            "git":             _git_info(self.repo_root),
            "python":          _python_info(),
            "platform":        _platform_info(),
            "packages":        _package_versions(),
            "config":          _config_info(self.config_path),
            "inputs":          _input_records(self.input_paths),
            "outputs":         [],
        }

    def _finish(self, *, exit_status: str) -> None:
        elapsed = time.monotonic() - self._start_time
        if self._metadata is None:
            raise RuntimeError(
                "ProvenanceRecorder.finish() called before start()"
            )
        self._metadata["runtime_seconds"] = round(elapsed, 4)
        self._metadata["exit_status"]     = exit_status
        self._metadata["outputs"]         = _output_records(self.output_dirs)
        _write_json(self._metadata, self.output_path)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> dict | None:
        """The collected metadata dict, or ``None`` before the run starts."""
        return self._metadata

    def get_output_path(self) -> Path:
        """Return the path where metadata was (or will be) written."""
        return self.output_path


# ---------------------------------------------------------------------------
# Functional wrapper
# ---------------------------------------------------------------------------


def record_run(
    func: Callable,
    *args,
    config_path:  str | Path | None    = None,
    input_paths:  Sequence[str | Path] = (),
    output_dirs:  Sequence[str | Path] = (),
    output_path:  str | Path           = DEFAULT_OUTPUT_PATH,
    repo_root:    str | Path | None    = None,
    **kwargs,
) -> None:
    """Call *func* with ``*args, **kwargs`` and record provenance metadata.

    This is a thin wrapper around :class:`ProvenanceRecorder` for callers who
    prefer a functional style::

        record_run(
            run_pipeline,
            config_path="config/config.yaml",
            input_paths=["data/processed/panel_clean.csv"],
            output_dirs=["tables", "figures"],
        )

    Parameters
    ----------
    func:
        The pipeline callable to wrap (e.g. ``run_pipeline``).  Called with
        the remaining positional and keyword arguments.
    config_path, input_paths, output_dirs, output_path, repo_root:
        Forwarded to :class:`ProvenanceRecorder`.

    Notes
    -----
    Exceptions raised by *func* are re-raised after the metadata is written.
    The ``exit_status`` field will contain ``"error: <ExceptionType>"`` in
    this case.
    """
    with ProvenanceRecorder(
        config_path=config_path,
        input_paths=input_paths,
        output_dirs=output_dirs,
        output_path=output_path,
        repo_root=repo_root,
    ):
        func(*args, **kwargs)
