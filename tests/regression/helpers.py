"""
tests/regression/helpers.py
============================
Reusable comparison utilities for regression-testing the AI & Productivity
research pipeline.  Each function is a drop-in assertion: it raises
``AssertionError`` with a detailed, diff-style message on failure and returns
``None`` on success.

Design principles
-----------------
1. **Fail loudly, fail informatively.**  Every assertion collects *all*
   differences within a comparison before raising, so a single test run
   surfaces the complete picture rather than stopping at the first mismatch.

2. **Configurable tolerances, explicit defaults.**  Numeric comparisons accept
   ``rtol`` (relative) and ``atol`` (absolute) thresholds following the
   ``numpy.testing`` convention::

       |actual - reference| <= atol + rtol * |reference|

   Defaults are conservative (``rtol=1e-5``, ``atol=0.0``) — tight enough to
   catch real regressions but loose enough to survive IEEE-754 rounding.

3. **No production code imported.**  This module depends only on the Python
   standard library plus ``pandas``, ``numpy``, and optionally ``Pillow``
   (for pixel-level figure comparison).

4. **Parquet support.**  ``assert_parquet_equal`` reads both files into
   DataFrames and delegates to ``assert_dataframe_equal``, so all tolerance
   parameters are available for Parquet comparisons too.

5. **LaTeX comparisons are text-level.**  Coefficient values embedded in
   LaTeX are compared as strings after whitespace normalisation; they are
   *not* parsed back into floats.  Numeric precision is enforced upstream,
   at the ``assert_coefficient_equal`` stage.

Typical usage
-------------
>>> from tests.regression import (
...     assert_csv_equal,
...     assert_parquet_equal,
...     assert_dataframe_equal,
...     assert_coefficient_equal,
...     assert_latex_equal,
...     assert_figure_equal,
... )
>>> assert_csv_equal("output/results.csv", "tests/fixtures/reference_outputs/tables/results.csv")
>>> assert_coefficient_equal(new_model, old_model, "ln_ai", rtol=1e-6)
>>> assert_figure_equal("output/trend.png",
...                     "tests/fixtures/reference_outputs/figures/trend.png",
...                     method="pixel", pixel_rms_tol=1.5)
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import textwrap
from typing import Literal, Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _label_prefix(label: str) -> str:
    return f"[{label}] " if label else ""


def _format_failures(failures: list[str], label: str) -> str:
    prefix = _label_prefix(label)
    lines = "\n".join(f"  • {f}" for f in failures)
    return f"{prefix}{len(failures)} difference(s) found:\n{lines}"


def _is_numeric_dtype(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series)


# ---------------------------------------------------------------------------
# Core DataFrame comparison
# ---------------------------------------------------------------------------

def assert_dataframe_equal(
    actual: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    rtol: float = 1e-5,
    atol: float = 0.0,
    check_column_order: bool = True,
    check_row_order: bool = True,
    check_index: bool = False,
    check_dtype: bool = False,
    ignore_columns: Sequence[str] | None = None,
    label: str = "",
) -> None:
    """Assert that *actual* and *reference* DataFrames are equal within tolerance.

    Numeric columns are compared with ``|actual - ref| <= atol + rtol * |ref|``
    using :func:`numpy.testing.assert_allclose`.  Non-numeric columns (strings,
    booleans, categoricals) are compared exactly, cell by cell.

    Parameters
    ----------
    actual:
        DataFrame produced by the code under test.
    reference:
        Frozen reference DataFrame (the scientific ground truth).
    rtol:
        Maximum relative difference allowed for each numeric cell.
        Default ``1e-5`` (0.001 %).
    atol:
        Maximum absolute difference allowed for each numeric cell.
        Default ``0.0``.
    check_column_order:
        When ``True`` (default), column order must match.  Set to ``False``
        to allow any permutation of the same set of column names.
    check_row_order:
        When ``True`` (default), row order must match.  Set to ``False``
        to sort both DataFrames by all shared columns before comparing.
    check_index:
        When ``True``, the DataFrame index must also match exactly.
        Default ``False`` (index is usually a meaningless integer range).
    check_dtype:
        When ``True``, column dtypes must match.  Default ``False`` —
        scientific outputs often mix ``int64``/``float64`` depending on
        the writing path.
    ignore_columns:
        Column names to skip entirely.  Useful for metadata columns
        (timestamps, run-IDs) that legitimately differ across runs.
    label:
        Short human-readable identifier prepended to error messages,
        e.g. ``"baseline_tfp_fe coefficients"``.

    Raises
    ------
    AssertionError
        With a human-readable summary of every difference found.
    """
    pfx = _label_prefix(label)
    ignore = set(ignore_columns or [])

    # ---- shape / columns ---------------------------------------------------
    actual_cols   = [c for c in actual.columns   if c not in ignore]
    ref_cols      = [c for c in reference.columns if c not in ignore]

    if check_column_order:
        if actual_cols != ref_cols:
            raise AssertionError(
                f"{pfx}Column mismatch.\n"
                f"  actual:    {actual_cols}\n"
                f"  reference: {ref_cols}"
            )
    else:
        if set(actual_cols) != set(ref_cols):
            extra    = sorted(set(actual_cols) - set(ref_cols))
            missing  = sorted(set(ref_cols) - set(actual_cols))
            parts = []
            if extra:   parts.append(f"extra in actual: {extra}")
            if missing: parts.append(f"missing from actual: {missing}")
            raise AssertionError(f"{pfx}Column name mismatch.  " + "  ".join(parts))
        # Align to reference order for element-wise comparison
        actual    = actual[ref_cols]
        reference = reference[ref_cols]

    if len(actual) != len(reference):
        raise AssertionError(
            f"{pfx}Row count mismatch: actual={len(actual)}, reference={len(reference)}"
        )

    if not check_row_order:
        sort_cols = list(ref_cols)
        actual    = actual.sort_values(sort_cols).reset_index(drop=True)
        reference = reference.sort_values(sort_cols).reset_index(drop=True)

    if check_index:
        if not actual.index.equals(reference.index):
            raise AssertionError(
                f"{pfx}Index mismatch.\n"
                f"  actual:    {actual.index.tolist()[:10]} …\n"
                f"  reference: {reference.index.tolist()[:10]} …"
            )

    # ---- per-column comparison ---------------------------------------------
    failures: list[str] = []

    for col in ref_cols:
        act_col = actual[col]
        ref_col = reference[col]

        if check_dtype and act_col.dtype != ref_col.dtype:
            failures.append(
                f"column '{col}': dtype {act_col.dtype!r} != {ref_col.dtype!r}"
            )

        if _is_numeric_dtype(ref_col):
            try:
                np.testing.assert_allclose(
                    act_col.to_numpy(dtype=float, na_value=np.nan),
                    ref_col.to_numpy(dtype=float, na_value=np.nan),
                    rtol=rtol,
                    atol=atol,
                    equal_nan=True,
                )
            except AssertionError as exc:
                # Extract the numpy summary line (first line) for brevity
                first_line = str(exc).split("\n")[0]
                failures.append(f"column '{col}' (numeric): {first_line}")
        else:
            # String / categorical / bool — exact comparison
            mismatches = np.where(act_col.fillna("__NaN__") != ref_col.fillna("__NaN__"))[0]
            if len(mismatches):
                sample = mismatches[:3]
                detail = "; ".join(
                    f"row {i}: {act_col.iloc[i]!r} != {ref_col.iloc[i]!r}"
                    for i in sample
                )
                suffix = f" (+{len(mismatches)-3} more)" if len(mismatches) > 3 else ""
                failures.append(f"column '{col}' (string): {detail}{suffix}")

    if failures:
        raise AssertionError(_format_failures(failures, label))


# ---------------------------------------------------------------------------
# CSV comparison
# ---------------------------------------------------------------------------

def assert_csv_equal(
    actual: str | pathlib.Path,
    reference: str | pathlib.Path,
    *,
    rtol: float = 1e-5,
    atol: float = 0.0,
    check_column_order: bool = True,
    check_row_order: bool = True,
    check_index: bool = False,
    check_dtype: bool = False,
    ignore_columns: Sequence[str] | None = None,
    csv_kwargs: dict | None = None,
    label: str = "",
) -> None:
    """Assert that two CSV files contain equal data within numeric tolerance.

    Both files are loaded with :func:`pandas.read_csv` using identical reader
    settings, then compared via :func:`assert_dataframe_equal`.

    Parameters
    ----------
    actual:
        Path to the CSV produced by the code under test.
    reference:
        Path to the frozen reference CSV (scientific ground truth).
    rtol:
        Maximum relative difference for numeric columns.  Default ``1e-5``.
    atol:
        Maximum absolute difference for numeric columns.  Default ``0.0``.
    check_column_order:
        Enforce column ordering.  Default ``True``.
    check_row_order:
        Enforce row ordering.  Default ``True``.
    check_index:
        Enforce that DataFrame indices match.  Default ``False``.
    check_dtype:
        Enforce column dtype equality.  Default ``False``.
    ignore_columns:
        Column names to skip during comparison.
    csv_kwargs:
        Extra keyword arguments forwarded to :func:`pandas.read_csv` for
        both files.  Example: ``{"sep": "\\t", "encoding": "latin-1"}``.
    label:
        Short identifier for error messages.

    Raises
    ------
    FileNotFoundError
        If either path does not exist.
    AssertionError
        With a diff-style summary of every column that differs.

    Notes
    -----
    CSV files do not encode dtypes, so columns containing integers in the
    reference may be read as ``float64`` in the actual output if any value is
    NaN.  This is why ``check_dtype`` defaults to ``False``.
    """
    actual    = pathlib.Path(actual)
    reference = pathlib.Path(reference)

    for p, name in [(actual, "actual"), (reference, "reference")]:
        if not p.exists():
            raise FileNotFoundError(f"assert_csv_equal: {name} path not found: {p}")

    kwargs = csv_kwargs or {}
    pfx    = _label_prefix(label)

    try:
        df_actual = pd.read_csv(actual, **kwargs)
    except Exception as exc:
        raise AssertionError(f"{pfx}Could not read actual CSV {actual}: {exc}") from exc

    try:
        df_ref = pd.read_csv(reference, **kwargs)
    except Exception as exc:
        raise AssertionError(f"{pfx}Could not read reference CSV {reference}: {exc}") from exc

    assert_dataframe_equal(
        df_actual,
        df_ref,
        rtol=rtol,
        atol=atol,
        check_column_order=check_column_order,
        check_row_order=check_row_order,
        check_index=check_index,
        check_dtype=check_dtype,
        ignore_columns=ignore_columns,
        label=label or str(actual.name),
    )


# ---------------------------------------------------------------------------
# Parquet comparison
# ---------------------------------------------------------------------------

def assert_parquet_equal(
    actual: str | pathlib.Path,
    reference: str | pathlib.Path,
    *,
    rtol: float = 1e-5,
    atol: float = 0.0,
    check_column_order: bool = True,
    check_row_order: bool = True,
    check_index: bool = False,
    check_dtype: bool = True,
    ignore_columns: Sequence[str] | None = None,
    label: str = "",
) -> None:
    """Assert that two Parquet datasets contain equal data within numeric tolerance.

    Both files are loaded with :func:`pandas.read_parquet`, then compared via
    :func:`assert_dataframe_equal`.

    Parameters
    ----------
    actual:
        Path to the Parquet file produced by the code under test.
    reference:
        Path to the frozen reference Parquet file.
    rtol:
        Maximum relative difference for numeric columns.  Default ``1e-5``.
    atol:
        Maximum absolute difference for numeric columns.  Default ``0.0``.
    check_column_order:
        Enforce column ordering.  Default ``True``.
    check_row_order:
        Enforce row ordering.  Default ``True``.
    check_index:
        Enforce that DataFrame indices match.  Default ``False``.
    check_dtype:
        Enforce column dtype equality.  Default ``True`` — unlike CSV, Parquet
        encodes dtypes precisely, so dtype changes are genuine regressions.
    ignore_columns:
        Column names to skip.
    label:
        Short identifier for error messages.

    Raises
    ------
    FileNotFoundError
        If either path does not exist.
    AssertionError
        With a diff-style summary of every column that differs.
    ImportError
        If ``pyarrow`` or ``fastparquet`` is not installed.
    """
    actual    = pathlib.Path(actual)
    reference = pathlib.Path(reference)

    for p, name in [(actual, "actual"), (reference, "reference")]:
        if not p.exists():
            raise FileNotFoundError(f"assert_parquet_equal: {name} path not found: {p}")

    pfx = _label_prefix(label)

    try:
        df_actual = pd.read_parquet(actual)
    except Exception as exc:
        raise AssertionError(f"{pfx}Could not read actual Parquet {actual}: {exc}") from exc

    try:
        df_ref = pd.read_parquet(reference)
    except Exception as exc:
        raise AssertionError(f"{pfx}Could not read reference Parquet {reference}: {exc}") from exc

    assert_dataframe_equal(
        df_actual,
        df_ref,
        rtol=rtol,
        atol=atol,
        check_column_order=check_column_order,
        check_row_order=check_row_order,
        check_index=check_index,
        check_dtype=check_dtype,
        ignore_columns=ignore_columns,
        label=label or str(actual.name),
    )


# ---------------------------------------------------------------------------
# Regression coefficient comparison
# ---------------------------------------------------------------------------

def _extract_coef_values(
    result,
    param_name: str,
) -> tuple[float, float | None, float | None, int | None]:
    """Extract ``(coef, se, pvalue, nobs)`` from *result*.

    *result* may be:

    * A **linearmodels** / **statsmodels** result object with attributes
      ``.params``, ``.std_errors`` (or ``.bse``), ``.pvalues``, ``.nobs``.
    * A **dict** with keys ``"coef"`` (required), ``"se"``, ``"pvalue"``,
      ``"nobs"`` (all optional).  Use this form when comparing against
      stored reference values from ``manifest.yaml``.

    Raises
    ------
    KeyError / AttributeError
        If *param_name* is not found or a required attribute is missing.
    """
    if isinstance(result, dict):
        if "coef" not in result:
            raise KeyError(
                f"Reference dict must contain key 'coef'; got: {list(result.keys())}"
            )
        coef   = float(result["coef"])
        se     = float(result["se"])     if "se"     in result else None
        pvalue = float(result["pvalue"]) if "pvalue" in result else None
        nobs   = int(result["nobs"])     if "nobs"   in result else None
        return coef, se, pvalue, nobs

    # Duck-typed result object (linearmodels or statsmodels)
    params = result.params
    if param_name not in params.index:
        available = list(params.index)
        raise KeyError(
            f"Parameter '{param_name}' not found in result.params.  "
            f"Available: {available}"
        )

    coef = float(params[param_name])

    # Standard errors — linearmodels uses .std_errors, statsmodels uses .bse
    _se_attr = getattr(result, "std_errors", None)
    if _se_attr is None:
        _se_attr = getattr(result, "bse", None)
    se = float(_se_attr[param_name]) if _se_attr is not None else None

    pvalues = getattr(result, "pvalues", None)
    pvalue  = float(pvalues[param_name]) if pvalues is not None else None

    nobs_raw = getattr(result, "nobs", None)
    nobs = int(nobs_raw) if nobs_raw is not None else None

    return coef, se, pvalue, nobs


def assert_coefficient_equal(
    actual_result,
    reference_result,
    param_name: str,
    *,
    rtol: float = 1e-6,
    atol: float = 0.0,
    check_se: bool = True,
    check_pvalue: bool = True,
    check_nobs: bool = False,
    label: str = "",
) -> None:
    """Assert that one regression coefficient matches across two model results.

    Compares the point estimate, standard error, and p-value for a single
    parameter.  Uses ``|actual - ref| <= atol + rtol * |ref|`` for each scalar.

    Parameters
    ----------
    actual_result:
        A regression result object (linearmodels / statsmodels) **or** a
        plain dict with keys ``"coef"``, ``"se"``, ``"pvalue"``, ``"nobs"``.
        The dict form is convenient when comparing against values stored in
        ``manifest.yaml``::

            assert_coefficient_equal(
                new_model,
                {"coef": -0.0098, "se": 0.0012, "pvalue": 0.0000, "nobs": 1545},
                "ln_ai",
            )
    reference_result:
        Same format as *actual_result*.
    param_name:
        Name of the parameter to compare, exactly as it appears in
        ``result.params.index``, e.g. ``"ln_ai"``, ``"ln_hc"``,
        ``"const"``.
    rtol:
        Maximum relative difference.  Default ``1e-6`` — tighter than CSV
        comparison because coefficient precision is critical for inference.
    atol:
        Maximum absolute difference.  Default ``0.0``.
    check_se:
        Compare standard errors.  Default ``True``.
    check_pvalue:
        Compare p-values.  Default ``True``.
    check_nobs:
        Compare observation counts (exact integer equality).  Default
        ``False`` — enable when you specifically want to verify sample size.
    label:
        Short identifier prepended to error messages, e.g. ``"robustness
        suite / baseline_tfp_fe"``.

    Raises
    ------
    KeyError
        If *param_name* is not found in one of the result objects.
    AssertionError
        With per-quantity diffs (coef, se, pvalue, nobs) for every check
        that failed.

    Notes
    -----
    When both *actual_result* and *reference_result* are dicts, this function
    compares plain float values; no regression library is imported.  This is
    intentional — it lets Sprint-2 tests freeze coefficient values in YAML
    and compare against them without requiring the full econometric stack.
    """
    pfx = _label_prefix(label)

    act_coef, act_se, act_pv, act_nobs = _extract_coef_values(actual_result, param_name)
    ref_coef, ref_se, ref_pv, ref_nobs = _extract_coef_values(reference_result, param_name)

    failures: list[str] = []

    def _check(name: str, act: float | None, ref: float | None) -> None:
        if act is None or ref is None:
            return  # one side doesn't have this quantity — skip silently
        try:
            np.testing.assert_allclose(act, ref, rtol=rtol, atol=atol)
        except AssertionError:
            rel_diff = abs(act - ref) / (abs(ref) + 1e-300)
            failures.append(
                f"{param_name}.{name}: actual={act:.10g}, reference={ref:.10g}, "
                f"abs_diff={abs(act-ref):.3e}, rel_diff={rel_diff:.3e}"
            )

    _check("coef",   act_coef, ref_coef)

    if check_se:
        _check("se", act_se, ref_se)

    if check_pvalue:
        _check("pvalue", act_pv, ref_pv)

    if check_nobs and act_nobs is not None and ref_nobs is not None:
        if act_nobs != ref_nobs:
            failures.append(
                f"{param_name}.nobs: actual={act_nobs}, reference={ref_nobs}"
            )

    if failures:
        raise AssertionError(_format_failures(failures, label))


# ---------------------------------------------------------------------------
# LaTeX comparison
# ---------------------------------------------------------------------------

def assert_latex_equal(
    actual: str,
    reference: str,
    *,
    normalize_whitespace: bool = True,
    ignore_patterns: Sequence[str] | None = None,
    label: str = "",
) -> None:
    """Assert that two LaTeX strings are equal (after optional normalisation).

    This is a **text-level** comparison.  Numeric values embedded in LaTeX
    (e.g. coefficient cells) are compared as strings, not re-parsed into
    floats.  Use :func:`assert_coefficient_equal` upstream to verify numeric
    precision before generating the LaTeX.

    Parameters
    ----------
    actual:
        LaTeX string produced by the code under test.
    reference:
        Frozen reference LaTeX string (scientific ground truth).
    normalize_whitespace:
        When ``True`` (default):

        * Leading/trailing whitespace is stripped.
        * Runs of whitespace (spaces, tabs) within a line are collapsed to
          a single space.
        * Blank lines are collapsed to a single blank line.
        * Trailing spaces at end-of-line are removed.

        This prevents spurious failures from formatting-only refactors.
    ignore_patterns:
        List of regular expressions.  Any substring in *both* strings that
        matches a pattern is replaced with a fixed placeholder before
        comparison.  Useful for timestamps, build IDs, or other volatile
        metadata embedded as LaTeX comments::

            ignore_patterns=[
                r"% Generated on .*",
                r"% git-hash: [0-9a-f]+",
            ]
    label:
        Short identifier for error messages.

    Raises
    ------
    AssertionError
        With the first differing line highlighted.

    Notes
    -----
    The comparison is performed line-by-line so the error message can report
    the *first* line that differs (unlike a plain ``==`` that only says
    "strings differ").
    """
    pfx = _label_prefix(label)

    def _normalise(text: str) -> str:
        if ignore_patterns:
            for pat in ignore_patterns:
                text = re.sub(pat, "__IGNORED__", text)
        if normalize_whitespace:
            lines = text.splitlines()
            lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in lines]
            # Collapse consecutive blank lines to one
            collapsed: list[str] = []
            prev_blank = False
            for line in lines:
                blank = line.strip() == ""
                if blank and prev_blank:
                    continue
                collapsed.append(line)
                prev_blank = blank
            text = "\n".join(collapsed).strip()
        return text

    act_norm = _normalise(actual)
    ref_norm = _normalise(reference)

    if act_norm == ref_norm:
        return

    # Build a per-line diff for the error message
    act_lines = act_norm.splitlines()
    ref_lines = ref_norm.splitlines()

    max_len = max(len(act_lines), len(ref_lines))
    diffs: list[str] = []
    for i in range(max_len):
        al = act_lines[i] if i < len(act_lines) else "<MISSING>"
        rl = ref_lines[i] if i < len(ref_lines) else "<MISSING>"
        if al != rl:
            diffs.append(f"  line {i+1}:")
            diffs.append(f"    actual:    {al!r}")
            diffs.append(f"    reference: {rl!r}")
            if len(diffs) > 24:  # cap at 8 mismatched lines
                diffs.append(f"  … ({max_len - i - 1} more lines not shown)")
                break

    detail = "\n".join(diffs)
    raise AssertionError(
        f"{pfx}LaTeX strings differ "
        f"(actual={len(act_lines)} lines, reference={len(ref_lines)} lines):\n{detail}"
    )


# ---------------------------------------------------------------------------
# Figure comparison
# ---------------------------------------------------------------------------

def _hash_compare(
    actual: pathlib.Path,
    reference: pathlib.Path,
    pfx: str,
) -> None:
    """Exact SHA-256 comparison of two files."""
    act_hash = _sha256(actual)
    ref_hash = _sha256(reference)
    if act_hash != ref_hash:
        raise AssertionError(
            f"{pfx}File hashes differ.\n"
            f"  actual:    {act_hash}  {actual.name}\n"
            f"  reference: {ref_hash}  {reference.name}"
        )


def _pixel_compare(
    actual: pathlib.Path,
    reference: pathlib.Path,
    pixel_rms_tol: float,
    max_pixel_diff: int | None,
    pfx: str,
) -> None:
    """Pixel-level RMS comparison for raster images (PNG, JPEG, TIFF)."""
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for pixel-level figure comparison.  "
            "Install it with:  pip install Pillow"
        ) from exc

    act_arr = np.array(Image.open(actual).convert("RGB"), dtype=float)
    ref_arr = np.array(Image.open(reference).convert("RGB"), dtype=float)

    if act_arr.shape != ref_arr.shape:
        raise AssertionError(
            f"{pfx}Image dimensions differ.\n"
            f"  actual:    {act_arr.shape}  (H×W×C)\n"
            f"  reference: {ref_arr.shape}"
        )

    diff   = act_arr - ref_arr
    rms    = float(np.sqrt(np.mean(diff ** 2)))
    max_d  = float(np.max(np.abs(diff)))
    n_diff = int(np.sum(np.abs(diff) > 0))

    failures: list[str] = []

    if rms > pixel_rms_tol:
        failures.append(
            f"RMS pixel difference {rms:.4f} exceeds tolerance {pixel_rms_tol:.4f} "
            f"(values on 0–255 scale)"
        )
    if max_pixel_diff is not None and max_d > max_pixel_diff:
        failures.append(
            f"Max per-pixel difference {max_d:.1f} exceeds max_pixel_diff={max_pixel_diff}"
        )

    if failures:
        failures.append(
            f"(pixels differing: {n_diff:,} / {act_arr.size:,}, "
            f"fraction: {n_diff/act_arr.size:.4%})"
        )
        raise AssertionError(_format_failures(failures, ""))


def _stats_compare(
    actual: pathlib.Path,
    reference: pathlib.Path,
    pixel_rms_tol: float,
    pfx: str,
) -> None:
    """Compare channel-wise image statistics rather than individual pixels.

    This mode is robust to minor rendering differences across OS/font versions.
    For each RGB channel it compares mean, standard deviation, and the 25th /
    50th / 75th percentiles.  If every statistic is within *pixel_rms_tol*
    (on the 0–255 scale), the comparison passes.
    """
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for stats-level figure comparison.  "
            "Install it with:  pip install Pillow"
        ) from exc

    act_arr = np.array(Image.open(actual).convert("RGB"), dtype=float)
    ref_arr = np.array(Image.open(reference).convert("RGB"), dtype=float)

    if act_arr.shape != ref_arr.shape:
        raise AssertionError(
            f"{pfx}Image dimensions differ.\n"
            f"  actual:    {act_arr.shape}\n"
            f"  reference: {ref_arr.shape}"
        )

    failures: list[str] = []
    channel_names = ("R", "G", "B")

    for c, ch in enumerate(channel_names):
        act_ch = act_arr[:, :, c].ravel()
        ref_ch = ref_arr[:, :, c].ravel()

        stats = {
            "mean":   (act_ch.mean(),                ref_ch.mean()),
            "std":    (act_ch.std(),                 ref_ch.std()),
            "p25":    (np.percentile(act_ch, 25),    np.percentile(ref_ch, 25)),
            "median": (np.percentile(act_ch, 50),    np.percentile(ref_ch, 50)),
            "p75":    (np.percentile(act_ch, 75),    np.percentile(ref_ch, 75)),
        }

        for stat_name, (act_val, ref_val) in stats.items():
            diff = abs(act_val - ref_val)
            if diff > pixel_rms_tol:
                failures.append(
                    f"channel {ch} {stat_name}: actual={act_val:.3f}, "
                    f"reference={ref_val:.3f}, diff={diff:.3f} > tol={pixel_rms_tol:.3f}"
                )

    if failures:
        raise AssertionError(_format_failures(failures, pfx.rstrip()))


def assert_figure_equal(
    actual: str | pathlib.Path,
    reference: str | pathlib.Path,
    *,
    method: Literal["hash", "pixel", "stats"] = "hash",
    pixel_rms_tol: float = 2.0,
    max_pixel_diff: int | None = None,
    label: str = "",
) -> None:
    """Assert that two image files represent equivalent figures.

    Three comparison modes are available:

    ``"hash"``  *(default)*
        Exact SHA-256 match.  The most stringent mode.  Fails if even one
        byte differs — including invisible metadata.  Use this when
        comparing outputs from the **same machine and matplotlib version**
        (e.g. CI regression tests).

    ``"pixel"``
        Pixel-by-pixel comparison using Pillow.  Raises if the RMS
        difference across all pixels (0–255 scale) exceeds *pixel_rms_tol*.
        Useful when minor anti-aliasing or font rendering differences are
        acceptable.  Requires ``Pillow``.

    ``"stats"``
        Compares per-channel image statistics (mean, std, quartiles) rather
        than individual pixels.  Passes as long as each statistic differs by
        at most *pixel_rms_tol*.  The most lenient mode — suited for
        cross-platform or cross-version rendering comparisons.  Requires
        ``Pillow``.

    Parameters
    ----------
    actual:
        Path to the figure produced by the code under test.
    reference:
        Path to the frozen reference figure.
    method:
        Comparison strategy: ``"hash"``, ``"pixel"``, or ``"stats"``.
    pixel_rms_tol:
        Tolerance for ``"pixel"`` and ``"stats"`` modes, on the 0–255
        pixel scale.  Default ``2.0`` (< 1 % of the full 8-bit range).
    max_pixel_diff:
        For ``"pixel"`` mode only: maximum allowed per-pixel difference.
        ``None`` (default) disables this additional check.
    label:
        Short identifier for error messages.

    Raises
    ------
    FileNotFoundError
        If either path does not exist.
    AssertionError
        Describing the difference found.
    ValueError
        If *method* is not one of the supported values.
    ImportError
        For ``"pixel"`` or ``"stats"`` mode if Pillow is not installed.

    Notes
    -----
    **PDF figures are not suitable for pixel comparison** because matplotlib
    embeds a ``CreationDate`` timestamp in the PDF metadata, so two PDFs
    generated at different times from identical data will have different
    SHA-256 hashes even if the visual content is identical.  For PDF
    regression tests, either:

    * Convert to PNG first (``pdftoppm``, ``pdf2image``), then compare
      with ``method="pixel"`` or ``method="stats"``.
    * Use ``method="hash"`` only when the PDF was generated in the same
      process and timestamping is disabled via ``matplotlib.rcParams``.
    """
    actual    = pathlib.Path(actual)
    reference = pathlib.Path(reference)
    pfx       = _label_prefix(label)

    for p, name in [(actual, "actual"), (reference, "reference")]:
        if not p.exists():
            raise FileNotFoundError(
                f"{pfx}assert_figure_equal: {name} path not found: {p}"
            )

    if method == "hash":
        _hash_compare(actual, reference, pfx)
    elif method == "pixel":
        _pixel_compare(actual, reference, pixel_rms_tol, max_pixel_diff, pfx)
    elif method == "stats":
        _stats_compare(actual, reference, pixel_rms_tol, pfx)
    else:
        raise ValueError(
            f"assert_figure_equal: unknown method {method!r}.  "
            "Expected one of: 'hash', 'pixel', 'stats'."
        )
