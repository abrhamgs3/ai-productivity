# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.1.0] — 2026-06-18

### Added
- Professional `src/ai_productivity/` package layout (Sprint 1).
- `pyproject.toml` replacing `requirements.txt`; package now installable via `uv pip install -e .`.
- CLI entry point `ai-productivity` with `--version` and `doctor` commands.
- Centralized structured logger (`ai_productivity.logging`).
- Domain-specific exception hierarchy (`AIProdError`, `DataValidationError`, `MergeError`, `PipelineError`, `ModelSpecificationError`).
- First automated test suite (`tests/test_exceptions.py`).
- `.gitignore` configured for Python research projects (excludes raw data, generated outputs, virtual environments).
- GitHub Actions CI workflow (install → test → lint on every push).

### Existing (pre-Sprint-1)
- Panel dataset: 25-column CSV, 193 countries × 2010–2024.
- Data sources: WDI, PWT, AI Index proxy, WGI, Barro-Lee.
- Econometric pipeline: baseline FE, two-way FE, trimmed FE, growth model, sensitivity suite, falsification suite.
- Visualization: scatter, trend, coefficient comparison, missingness profile.
- Paper: LaTeX source, submission package, appendix.
