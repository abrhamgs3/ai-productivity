"""
tests/regression/conftest.py
==============================
Shared pytest fixtures for the regression helper unit-tests.

All fixtures produce synthetic, self-contained data so that the helper tests
never touch the real pipeline outputs or the reference fixtures in
``tests/fixtures/reference_outputs/``.
"""

from __future__ import annotations

import io
import pathlib
import tempfile

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# MockResult — a minimal duck-typed regression result object
# ---------------------------------------------------------------------------

class MockResult:
    """Duck-type the subset of linearmodels / statsmodels result API used by
    :func:`~tests.regression.helpers.assert_coefficient_equal`.

    Attributes
    ----------
    params:       pandas.Series  — point estimates indexed by param name
    std_errors:   pandas.Series  — standard errors (same index)
    pvalues:      pandas.Series  — p-values (same index)
    nobs:         int             — observation count
    """

    def __init__(
        self,
        params: dict[str, float],
        std_errors: dict[str, float],
        pvalues: dict[str, float],
        nobs: int = 1545,
    ) -> None:
        self.params     = pd.Series(params)
        self.std_errors = pd.Series(std_errors)
        self.pvalues    = pd.Series(pvalues)
        self.nobs       = nobs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def numeric_df() -> pd.DataFrame:
    """A small numeric-only DataFrame with known values."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "country_id": np.arange(1, 11, dtype=int),
            "year":       np.tile([2010, 2015], 5),
            "ln_tfp":     rng.uniform(-1.5, 1.5, 10),
            "ln_ai":      rng.uniform(-2.0, 0.5, 10),
            "ln_hc":      rng.uniform(0.8, 2.5, 10),
        }
    )


@pytest.fixture()
def mixed_df() -> pd.DataFrame:
    """DataFrame with both numeric and string columns."""
    return pd.DataFrame(
        {
            "iso3":   ["AFG", "ALB", "DZA", "AGO", "ARG"],
            "year":   [2000, 2001, 2002, 2003, 2004],
            "region": ["Asia", "Europe", "Africa", "Africa", "Americas"],
            "value":  [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )


@pytest.fixture()
def tmp_csv(tmp_path: pathlib.Path, numeric_df: pd.DataFrame):
    """Write *numeric_df* to a temporary CSV and return its path."""
    csv_path = tmp_path / "test_data.csv"
    numeric_df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture()
def reference_csv(tmp_path: pathlib.Path, numeric_df: pd.DataFrame):
    """Write *numeric_df* to a second temporary CSV (the 'reference')."""
    csv_path = tmp_path / "reference_data.csv"
    numeric_df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture()
def mock_result() -> MockResult:
    """A reference regression result with known coefficient values."""
    return MockResult(
        params     = {"ln_ai": -0.0098, "ln_hc": 0.3521, "const": 2.1043},
        std_errors = {"ln_ai":  0.0012, "ln_hc": 0.0421, "const": 0.1102},
        pvalues    = {"ln_ai":  0.0000, "ln_hc": 0.0000, "const": 0.0000},
        nobs       = 1545,
    )


@pytest.fixture()
def mock_result_perturbed(mock_result: MockResult) -> MockResult:
    """A result identical to *mock_result* except for tiny perturbations."""
    p  = mock_result.params.to_dict()
    se = mock_result.std_errors.to_dict()
    pv = mock_result.pvalues.to_dict()
    # Perturb ln_ai coefficient by 1e-8 — within any reasonable rtol
    p["ln_ai"]  += 1e-10
    se["ln_ai"] += 1e-11
    return MockResult(params=p, std_errors=se, pvalues=pv, nobs=mock_result.nobs)


@pytest.fixture()
def tiny_png(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a small 10×10 red PNG and return its path."""
    try:
        from PIL import Image  # type: ignore[import]
        img = Image.new("RGB", (10, 10), color=(200, 50, 50))
        path = tmp_path / "tiny.png"
        img.save(str(path))
        return path
    except ImportError:
        pytest.skip("Pillow not installed — pixel figure tests skipped")


@pytest.fixture()
def tiny_png_copy(tmp_path: pathlib.Path, tiny_png: pathlib.Path) -> pathlib.Path:
    """An exact byte-for-byte copy of *tiny_png*."""
    import shutil
    copy = tmp_path / "tiny_copy.png"
    shutil.copy2(tiny_png, copy)
    return copy


@pytest.fixture()
def tiny_png_different(tmp_path: pathlib.Path) -> pathlib.Path:
    """A slightly different 10×10 PNG (blue instead of red)."""
    try:
        from PIL import Image  # type: ignore[import]
        img = Image.new("RGB", (10, 10), color=(50, 50, 200))
        path = tmp_path / "tiny_diff.png"
        img.save(str(path))
        return path
    except ImportError:
        pytest.skip("Pillow not installed — pixel figure tests skipped")


@pytest.fixture()
def sample_latex() -> str:
    return textwrap.dedent(r"""
        \begin{tabular}{lccc}
        \hline
        Variable & Coef. & SE & p \\
        \hline
        ln\_ai & -0.0098 & 0.0012 & 0.000 \\
        ln\_hc &  0.3521 & 0.0421 & 0.000 \\
        \hline
        \end{tabular}
    """).strip()


import textwrap  # noqa: E402  (needed by sample_latex fixture)
