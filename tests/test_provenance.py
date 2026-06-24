"""
tests/test_provenance.py
=========================
Unit tests for ``src/ai_productivity/provenance.py``.

All tests are fully self-contained; they do not touch the real pipeline,
the reference fixtures, or ``outputs/provenance/``.
"""

from __future__ import annotations

import json
import pathlib
import time
import uuid

import pytest

from ai_productivity.provenance import (
    DEFAULT_OUTPUT_PATH,
    SCHEMA_VERSION,
    TRACKED_PACKAGES,
    ProvenanceRecorder,
    _config_info,
    _git_info,
    _input_records,
    _output_records,
    _package_versions,
    _platform_info,
    _python_info,
    _sha256_file,
    record_run,
)


# ===========================================================================
# _sha256_file
# ===========================================================================

class TestSha256File:
    def test_known_content(self, tmp_path: pathlib.Path) -> None:
        import hashlib
        p = tmp_path / "f.txt"
        data = b"hello provenance"
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_file(p) == expected

    def test_nonexistent_returns_none(self, tmp_path: pathlib.Path) -> None:
        assert _sha256_file(tmp_path / "ghost.txt") is None


# ===========================================================================
# Static info collectors
# ===========================================================================

class TestStaticInfo:
    def test_python_info_keys(self) -> None:
        info = _python_info()
        assert set(info.keys()) == {"version", "implementation", "executable"}
        assert info["version"].count(".") == 2  # major.minor.micro

    def test_platform_info_keys(self) -> None:
        info = _platform_info()
        assert set(info.keys()) == {"system", "release", "machine", "node_hash"}
        # node_hash is 12 hex chars
        assert len(info["node_hash"]) == 12
        int(info["node_hash"], 16)  # must be valid hex

    def test_package_versions_returns_dict(self) -> None:
        versions = _package_versions()
        assert isinstance(versions, dict)
        # Every tracked package has an entry (value may be None)
        for pkg in TRACKED_PACKAGES:
            assert pkg in versions

    def test_known_package_has_version(self) -> None:
        versions = _package_versions()
        # pandas is always installed in this project
        assert versions["pandas"] is not None
        assert versions["pandas"].count(".") >= 1

    def test_uninstalled_package_is_none(self) -> None:
        versions = _package_versions()
        # scikit-learn is NOT in this project's requirements
        assert versions.get("scikit-learn") is None

    def test_git_info_keys(self) -> None:
        info = _git_info(None)
        assert set(info.keys()) == {"commit", "branch", "dirty", "tags"}

    def test_git_commit_is_sha_or_none(self) -> None:
        info = _git_info(None)
        if info["commit"] is not None:
            assert len(info["commit"]) == 40
            int(info["commit"], 16)   # valid hex

    def test_git_tags_is_list(self) -> None:
        info = _git_info(None)
        assert isinstance(info["tags"], list)


# ===========================================================================
# _config_info
# ===========================================================================

class TestConfigInfo:
    def test_none_returns_none(self) -> None:
        assert _config_info(None) is None

    def test_existing_file(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text("key: value\n", encoding="utf-8")
        info = _config_info(p)
        assert info is not None
        assert info["path"] == str(p)
        assert info["sha256"] is not None
        assert len(info["sha256"]) == 64    # SHA-256 hex
        assert "key: value" in info["content_preview"]

    def test_preview_truncated_at_512(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "big.yaml"
        p.write_text("x" * 1000, encoding="utf-8")
        info = _config_info(p)
        assert info is not None
        assert len(info["content_preview"]) == 512

    def test_missing_file(self, tmp_path: pathlib.Path) -> None:
        info = _config_info(tmp_path / "nonexistent.yaml")
        assert info is not None
        assert info["sha256"] is None
        assert info["content_preview"] is None


# ===========================================================================
# _input_records / _output_records
# ===========================================================================

class TestRecords:
    def test_input_existing_file(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        recs = _input_records([p])
        assert len(recs) == 1
        r = recs[0]
        assert r["path"] == str(p)
        assert r["sha256"] is not None
        assert r["size_bytes"] == p.stat().st_size
        assert r["mtime_utc"] is not None
        assert "warning" not in r

    def test_input_missing_file(self, tmp_path: pathlib.Path) -> None:
        ghost = tmp_path / "ghost.csv"
        recs  = _input_records([ghost])
        r = recs[0]
        assert r["sha256"] is None
        assert r["size_bytes"] is None
        assert "warning" in r

    def test_output_scans_recursively(self, tmp_path: pathlib.Path) -> None:
        sub = tmp_path / "tables"
        sub.mkdir()
        (sub / "a.txt").write_text("hello")
        (sub / "sub").mkdir()
        (sub / "sub" / "b.txt").write_text("world")
        recs = _output_records([sub])
        paths = [r["path"] for r in recs]
        assert any("a.txt" in p for p in paths)
        assert any("b.txt" in p for p in paths)

    def test_output_sorted_by_path(self, tmp_path: pathlib.Path) -> None:
        d = tmp_path / "out"
        d.mkdir()
        (d / "z.txt").write_text("z")
        (d / "a.txt").write_text("a")
        recs = _output_records([d])
        paths = [r["path"] for r in recs]
        assert paths == sorted(paths)

    def test_output_missing_dir_ignored(self, tmp_path: pathlib.Path) -> None:
        recs = _output_records([tmp_path / "nonexistent"])
        assert recs == []


# ===========================================================================
# ProvenanceRecorder — context manager
# ===========================================================================

class TestProvenanceRecorder:
    def test_happy_path_writes_json(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_path=out):
            time.sleep(0.01)   # ensure measurable runtime
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["exit_status"] == "success"
        assert data["runtime_seconds"] > 0

    def test_metadata_keys_complete(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_path=out):
            pass
        data = json.loads(out.read_text())
        required = {
            "schema_version", "run_id", "timestamp_utc", "runtime_seconds",
            "exit_status", "git", "python", "platform", "packages",
            "config", "inputs", "outputs",
        }
        assert required <= set(data.keys())

    def test_schema_version_matches_constant(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_path=out):
            pass
        data = json.loads(out.read_text())
        assert data["schema_version"] == SCHEMA_VERSION

    def test_run_id_is_uuid(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_path=out):
            pass
        data = json.loads(out.read_text())
        uuid.UUID(data["run_id"])   # raises if not a valid UUID

    def test_pipeline_exception_is_reraised(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with pytest.raises(RuntimeError, match="pipeline blew up"):
            with ProvenanceRecorder(output_path=out):
                raise RuntimeError("pipeline blew up")
        # Metadata must still be written
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["exit_status"] == "error: RuntimeError"

    def test_config_recorded(self, tmp_path: pathlib.Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("param: 42\n")
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(config_path=cfg, output_path=out):
            pass
        data = json.loads(out.read_text())
        assert data["config"] is not None
        assert "param: 42" in data["config"]["content_preview"]

    def test_no_config_is_null(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_path=out):
            pass
        data = json.loads(out.read_text())
        assert data["config"] is None

    def test_input_paths_recorded(self, tmp_path: pathlib.Path) -> None:
        csv = tmp_path / "data.csv"
        csv.write_text("a,b\n1,2\n")
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(input_paths=[csv], output_path=out):
            pass
        data = json.loads(out.read_text())
        assert len(data["inputs"]) == 1
        assert data["inputs"][0]["sha256"] is not None

    def test_output_dirs_scanned(self, tmp_path: pathlib.Path) -> None:
        tables = tmp_path / "tables"
        tables.mkdir()
        (tables / "result.txt").write_text("coef: 0.01")
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_dirs=[tables], output_path=out):
            pass
        data = json.loads(out.read_text())
        assert any("result.txt" in r["path"] for r in data["outputs"])

    def test_parent_dir_created_automatically(self, tmp_path: pathlib.Path) -> None:
        out = tmp_path / "deep" / "nested" / "meta.json"
        with ProvenanceRecorder(output_path=out):
            pass
        assert out.exists()

    def test_metadata_property_accessible(self, tmp_path: pathlib.Path) -> None:
        rec = ProvenanceRecorder(output_path=tmp_path / "m.json")
        assert rec.metadata is None
        with rec:
            assert rec.metadata is not None
            assert "run_id" in rec.metadata

    def test_two_runs_get_different_run_ids(self, tmp_path: pathlib.Path) -> None:
        out1 = tmp_path / "m1.json"
        out2 = tmp_path / "m2.json"
        with ProvenanceRecorder(output_path=out1):
            pass
        with ProvenanceRecorder(output_path=out2):
            pass
        d1 = json.loads(out1.read_text())
        d2 = json.loads(out2.read_text())
        assert d1["run_id"] != d2["run_id"]

    def test_output_files_have_sha256(self, tmp_path: pathlib.Path) -> None:
        tables = tmp_path / "out"
        tables.mkdir()
        (tables / "x.txt").write_text("important result")
        out = tmp_path / "meta.json"
        with ProvenanceRecorder(output_dirs=[tables], output_path=out):
            pass
        data  = json.loads(out.read_text())
        recs  = data["outputs"]
        assert all(r["sha256"] is not None for r in recs)
        assert all(len(r["sha256"]) == 64 for r in recs)


# ===========================================================================
# record_run functional wrapper
# ===========================================================================

class TestRecordRun:
    def test_wraps_callable(self, tmp_path: pathlib.Path) -> None:
        calls = []
        def dummy_pipeline():
            calls.append(1)

        out = tmp_path / "meta.json"
        record_run(dummy_pipeline, output_path=out)
        assert calls == [1]
        assert out.exists()

    def test_passes_args_and_kwargs(self, tmp_path: pathlib.Path) -> None:
        results = []
        def dummy(x, y=10):
            results.append((x, y))

        out = tmp_path / "meta.json"
        record_run(dummy, 42, y=99, output_path=out)
        assert results == [(42, 99)]

    def test_exception_reraises(self, tmp_path: pathlib.Path) -> None:
        def bad():
            raise ValueError("nope")

        out = tmp_path / "meta.json"
        with pytest.raises(ValueError, match="nope"):
            record_run(bad, output_path=out)
        data = json.loads(out.read_text())
        assert data["exit_status"] == "error: ValueError"
