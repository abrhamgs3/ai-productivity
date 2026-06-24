"""
tests/regression/test_helpers.py
==================================
Unit tests for every comparison utility in ``tests.regression.helpers``.

Each test class targets one public function.  Tests are intentionally small
and self-contained — they generate all data synthetically so they never
depend on the real pipeline outputs or the reference fixtures in
``tests/fixtures/reference_outputs/``.

Coverage targets
----------------
assert_csv_equal            9 tests
assert_dataframe_equal     10 tests
assert_parquet_equal        3 tests   (smoke-tests; relies on assert_dataframe_equal)
assert_coefficient_equal   10 tests
assert_latex_equal          8 tests
assert_figure_equal         8 tests
                           --------
Total                      48 tests
"""

from __future__ import annotations

import pathlib
import shutil
import textwrap

import numpy as np
import pandas as pd
import pytest

from tests.regression.helpers import (
    assert_coefficient_equal,
    assert_csv_equal,
    assert_dataframe_equal,
    assert_figure_equal,
    assert_latex_equal,
    assert_parquet_equal,
)

# Re-import MockResult from conftest so we can construct it directly in tests
# that don't use the fixture.
from tests.regression.conftest import MockResult


# ===========================================================================
# assert_csv_equal
# ===========================================================================


class TestAssertCsvEqual:
    """Tests for :func:`assert_csv_equal`."""

    def test_identical_csv_passes(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Comparing a file against itself must always pass."""
        p = tmp_path / "data.csv"
        numeric_df.to_csv(p, index=False)
        assert_csv_equal(p, p)

    def test_float_within_rtol_passes(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Floats perturbed within rtol must not raise."""
        ref_path = tmp_path / "reference.csv"
        act_path = tmp_path / "actual.csv"
        numeric_df.to_csv(ref_path, index=False)
        perturbed = numeric_df.copy()
        perturbed["ln_tfp"] += perturbed["ln_tfp"].abs() * 1e-7  # well inside 1e-5
        perturbed.to_csv(act_path, index=False)
        assert_csv_equal(act_path, ref_path, rtol=1e-5)

    def test_float_beyond_rtol_fails(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Floats perturbed beyond rtol must raise AssertionError."""
        ref_path = tmp_path / "reference.csv"
        act_path = tmp_path / "actual.csv"
        numeric_df.to_csv(ref_path, index=False)
        perturbed = numeric_df.copy()
        perturbed["ln_tfp"] += 0.05  # 5 % absolute shift, >> rtol=1e-5
        perturbed.to_csv(act_path, index=False)
        with pytest.raises(AssertionError, match="ln_tfp"):
            assert_csv_equal(act_path, ref_path, rtol=1e-5)

    def test_string_mismatch_fails(
        self, tmp_path: pathlib.Path, mixed_df: pd.DataFrame
    ) -> None:
        """A changed string value in a non-numeric column must raise."""
        ref_path = tmp_path / "ref.csv"
        act_path = tmp_path / "act.csv"
        mixed_df.to_csv(ref_path, index=False)
        changed = mixed_df.copy()
        changed.loc[0, "region"] = "CHANGED"
        changed.to_csv(act_path, index=False)
        with pytest.raises(AssertionError, match="region"):
            assert_csv_equal(act_path, ref_path)

    def test_missing_column_fails(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Actual CSV missing a reference column must raise."""
        ref_path = tmp_path / "ref.csv"
        act_path = tmp_path / "act.csv"
        numeric_df.to_csv(ref_path, index=False)
        numeric_df.drop(columns=["ln_ai"]).to_csv(act_path, index=False)
        with pytest.raises(AssertionError, match="[Cc]olumn"):
            assert_csv_equal(act_path, ref_path)

    def test_different_row_count_fails(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Actual CSV with fewer rows must raise."""
        ref_path = tmp_path / "ref.csv"
        act_path = tmp_path / "act.csv"
        numeric_df.to_csv(ref_path, index=False)
        numeric_df.iloc[:5].to_csv(act_path, index=False)
        with pytest.raises(AssertionError, match="[Rr]ow count"):
            assert_csv_equal(act_path, ref_path)

    def test_column_order_ignored(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        """Reordered columns must pass when check_column_order=False."""
        ref_path = tmp_path / "ref.csv"
        act_path = tmp_path / "act.csv"
        numeric_df.to_csv(ref_path, index=False)
        numeric_df[list(reversed(numeric_df.columns))].to_csv(act_path, index=False)
        assert_csv_equal(act_path, ref_path, check_column_order=False)

    def test_ignore_columns_skipped(
        self, tmp_path: pathlib.Path, mixed_df: pd.DataFrame
    ) -> None:
        """Changes in ignored columns must not raise."""
        ref_path = tmp_path / "ref.csv"
        act_path = tmp_path / "act.csv"
        mixed_df.to_csv(ref_path, index=False)
        changed = mixed_df.copy()
        changed["region"] = "ANYTHING"
        changed.to_csv(act_path, index=False)
        assert_csv_equal(act_path, ref_path, ignore_columns=["region"])

    def test_missing_file_raises_fnf(self, tmp_path: pathlib.Path) -> None:
        """A non-existent path must raise FileNotFoundError, not AssertionError."""
        ghost = tmp_path / "does_not_exist.csv"
        real  = tmp_path / "real.csv"
        pd.DataFrame({"a": [1]}).to_csv(real, index=False)
        with pytest.raises(FileNotFoundError):
            assert_csv_equal(ghost, real)


# ===========================================================================
# assert_dataframe_equal
# ===========================================================================


class TestAssertDataFrameEqual:
    """Tests for :func:`assert_dataframe_equal`."""

    def test_identical_passes(self, numeric_df: pd.DataFrame) -> None:
        assert_dataframe_equal(numeric_df, numeric_df.copy())

    def test_float_within_tolerance_passes(self, numeric_df: pd.DataFrame) -> None:
        perturbed = numeric_df.copy()
        perturbed["ln_tfp"] += perturbed["ln_tfp"].abs() * 5e-7  # inside rtol=1e-5
        assert_dataframe_equal(perturbed, numeric_df, rtol=1e-5)

    def test_float_beyond_tolerance_fails(self, numeric_df: pd.DataFrame) -> None:
        perturbed = numeric_df.copy()
        perturbed["ln_ai"] += 1.0  # massive shift
        with pytest.raises(AssertionError, match="ln_ai"):
            assert_dataframe_equal(perturbed, numeric_df, rtol=1e-5)

    def test_atol_respected(self, numeric_df: pd.DataFrame) -> None:
        """A small absolute shift within atol must pass even with rtol=0."""
        perturbed = numeric_df.copy()
        perturbed["ln_hc"] += 0.0005
        assert_dataframe_equal(perturbed, numeric_df, rtol=0.0, atol=0.001)

    def test_nan_equal_nan(self) -> None:
        """NaN in both actual and reference at the same position must pass."""
        df = pd.DataFrame({"x": [1.0, np.nan, 3.0]})
        assert_dataframe_equal(df, df.copy())

    def test_row_count_mismatch_fails(self, numeric_df: pd.DataFrame) -> None:
        with pytest.raises(AssertionError, match="[Rr]ow count"):
            assert_dataframe_equal(numeric_df.iloc[:5], numeric_df)

    def test_column_mismatch_fails(self, numeric_df: pd.DataFrame) -> None:
        with pytest.raises(AssertionError, match="[Cc]olumn"):
            assert_dataframe_equal(
                numeric_df.drop(columns=["ln_hc"]), numeric_df
            )

    def test_string_mismatch_fails(self, mixed_df: pd.DataFrame) -> None:
        changed = mixed_df.copy()
        changed.loc[2, "iso3"] = "XXX"
        with pytest.raises(AssertionError, match="iso3"):
            assert_dataframe_equal(changed, mixed_df)

    def test_check_column_order_false(self, numeric_df: pd.DataFrame) -> None:
        reordered = numeric_df[list(reversed(numeric_df.columns))]
        assert_dataframe_equal(reordered, numeric_df, check_column_order=False)

    def test_label_appears_in_error(self, numeric_df: pd.DataFrame) -> None:
        """The label parameter must appear in the AssertionError message."""
        perturbed = numeric_df.copy()
        perturbed["ln_ai"] += 99.9
        with pytest.raises(AssertionError, match="MY_LABEL"):
            assert_dataframe_equal(perturbed, numeric_df, label="MY_LABEL")


# ===========================================================================
# assert_parquet_equal  (smoke tests — full logic is in assert_dataframe_equal)
# ===========================================================================


class TestAssertParquetEqual:
    """Smoke tests for :func:`assert_parquet_equal`."""

    def test_identical_passes(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        p = tmp_path / "data.parquet"
        numeric_df.to_parquet(p, index=False)
        assert_parquet_equal(p, p)

    def test_numeric_difference_fails(
        self, tmp_path: pathlib.Path, numeric_df: pd.DataFrame
    ) -> None:
        ref = tmp_path / "ref.parquet"
        act = tmp_path / "act.parquet"
        numeric_df.to_parquet(ref, index=False)
        perturbed = numeric_df.copy()
        perturbed["ln_tfp"] += 5.0
        perturbed.to_parquet(act, index=False)
        with pytest.raises(AssertionError):
            assert_parquet_equal(act, ref)

    def test_missing_file_raises_fnf(self, tmp_path: pathlib.Path) -> None:
        ghost = tmp_path / "ghost.parquet"
        real  = tmp_path / "real.parquet"
        pd.DataFrame({"a": [1.0]}).to_parquet(real, index=False)
        with pytest.raises(FileNotFoundError):
            assert_parquet_equal(ghost, real)


# ===========================================================================
# assert_coefficient_equal
# ===========================================================================


class TestAssertCoefficientEqual:
    """Tests for :func:`assert_coefficient_equal`."""

    def test_identical_result_objects_pass(self, mock_result: MockResult) -> None:
        assert_coefficient_equal(mock_result, mock_result, "ln_ai")

    def test_within_rtol_passes(
        self, mock_result: MockResult, mock_result_perturbed: MockResult
    ) -> None:
        """A perturbation of 1e-8 is well inside rtol=1e-6."""
        assert_coefficient_equal(
            mock_result_perturbed, mock_result, "ln_ai", rtol=1e-6
        )

    def test_coef_beyond_rtol_fails(self, mock_result: MockResult) -> None:
        bad = MockResult(
            params     = {"ln_ai": -0.0200, "ln_hc": 0.3521, "const": 2.1043},
            std_errors = mock_result.std_errors.to_dict(),
            pvalues    = mock_result.pvalues.to_dict(),
            nobs       = mock_result.nobs,
        )
        with pytest.raises(AssertionError, match="ln_ai.coef"):
            assert_coefficient_equal(bad, mock_result, "ln_ai", rtol=1e-6)

    def test_se_beyond_rtol_fails(self, mock_result: MockResult) -> None:
        bad = MockResult(
            params     = mock_result.params.to_dict(),
            std_errors = {"ln_ai": 0.9999, "ln_hc": 0.0421, "const": 0.1102},
            pvalues    = mock_result.pvalues.to_dict(),
            nobs       = mock_result.nobs,
        )
        with pytest.raises(AssertionError, match="ln_ai.se"):
            assert_coefficient_equal(bad, mock_result, "ln_ai", rtol=1e-6)

    def test_pvalue_beyond_rtol_fails(self, mock_result: MockResult) -> None:
        bad = MockResult(
            params     = mock_result.params.to_dict(),
            std_errors = mock_result.std_errors.to_dict(),
            pvalues    = {"ln_ai": 0.95, "ln_hc": 0.0000, "const": 0.0000},
            nobs       = mock_result.nobs,
        )
        with pytest.raises(AssertionError, match="ln_ai.pvalue"):
            assert_coefficient_equal(bad, mock_result, "ln_ai", rtol=1e-6)

    def test_check_se_false_skips_se(self, mock_result: MockResult) -> None:
        bad_se = MockResult(
            params     = mock_result.params.to_dict(),
            std_errors = {"ln_ai": 99.0, "ln_hc": 99.0, "const": 99.0},
            pvalues    = mock_result.pvalues.to_dict(),
            nobs       = mock_result.nobs,
        )
        # SE is wrong but check_se=False means it should be ignored
        assert_coefficient_equal(bad_se, mock_result, "ln_ai", check_se=False)

    def test_nobs_mismatch_fails(self, mock_result: MockResult) -> None:
        other_nobs = MockResult(
            params     = mock_result.params.to_dict(),
            std_errors = mock_result.std_errors.to_dict(),
            pvalues    = mock_result.pvalues.to_dict(),
            nobs       = 999,  # wrong sample size
        )
        with pytest.raises(AssertionError, match="nobs"):
            assert_coefficient_equal(
                other_nobs, mock_result, "ln_ai", check_nobs=True
            )

    def test_missing_param_raises_key_error(self, mock_result: MockResult) -> None:
        with pytest.raises(KeyError, match="nonexistent_var"):
            assert_coefficient_equal(mock_result, mock_result, "nonexistent_var")

    def test_dict_reference(self, mock_result: MockResult) -> None:
        """Comparison against a plain dict (stored reference values) must work."""
        ref_dict = {
            "coef":   -0.0098,
            "se":      0.0012,
            "pvalue":  0.0000,
            "nobs":    1545,
        }
        assert_coefficient_equal(mock_result, ref_dict, "ln_ai", rtol=1e-4)

    def test_dict_missing_coef_raises(self, mock_result: MockResult) -> None:
        """A reference dict without 'coef' must raise KeyError, not AttributeError."""
        bad_dict = {"se": 0.0012, "pvalue": 0.0000}
        with pytest.raises(KeyError, match="coef"):
            assert_coefficient_equal(mock_result, bad_dict, "ln_ai")


# ===========================================================================
# assert_latex_equal
# ===========================================================================


class TestAssertLatexEqual:
    """Tests for :func:`assert_latex_equal`."""

    LATEX = textwrap.dedent(r"""
        \begin{tabular}{lcc}
        \hline
        ln\_ai & -0.0098 & 0.000 \\
        \hline
        \end{tabular}
    """).strip()

    def test_identical_passes(self) -> None:
        assert_latex_equal(self.LATEX, self.LATEX)

    def test_whitespace_normalised(self) -> None:
        """Extra spaces around content must not cause failure."""
        with_spaces = self.LATEX.replace("-0.0098", "  -0.0098  ")
        assert_latex_equal(with_spaces, self.LATEX, normalize_whitespace=True)

    def test_trailing_newlines_normalised(self) -> None:
        """Trailing blank lines must not matter when normalize_whitespace=True."""
        assert_latex_equal(self.LATEX + "\n\n\n", self.LATEX, normalize_whitespace=True)

    def test_substantive_difference_fails(self) -> None:
        """A changed coefficient value must always raise."""
        changed = self.LATEX.replace("-0.0098", "-0.9999")
        with pytest.raises(AssertionError, match="-0.9999"):
            assert_latex_equal(changed, self.LATEX)

    def test_ignore_timestamp_pattern(self) -> None:
        """Patterns matching both strings must be replaced before comparison."""
        act = self.LATEX + "\n% Generated on 2026-06-23"
        ref = self.LATEX + "\n% Generated on 2025-01-01"
        # Without ignore_patterns these differ
        with pytest.raises(AssertionError):
            assert_latex_equal(act, ref)
        # With ignore_patterns they should be equal
        assert_latex_equal(
            act, ref, ignore_patterns=[r"% Generated on .*"]
        )

    def test_custom_ignore_pattern(self) -> None:
        """Any custom regex is substituted in both strings before comparison."""
        act = self.LATEX + "\n% hash: abc123def"
        ref = self.LATEX + "\n% hash: 999zzzzzz"
        assert_latex_equal(
            act, ref, ignore_patterns=[r"% hash: [0-9a-z]+"]
        )

    def test_line_number_in_error(self) -> None:
        """Error message must mention a line number so failures are locatable."""
        changed = self.LATEX.replace("-0.0098", "-WRONG")
        with pytest.raises(AssertionError, match=r"line \d+"):
            assert_latex_equal(changed, self.LATEX)

    def test_normalize_false_catches_whitespace(self) -> None:
        """With normalize_whitespace=False, extra spaces must cause failure."""
        with_spaces = self.LATEX.replace("-0.0098", "  -0.0098  ")
        with pytest.raises(AssertionError):
            assert_latex_equal(
                with_spaces, self.LATEX, normalize_whitespace=False
            )


# ===========================================================================
# assert_figure_equal
# ===========================================================================


class TestAssertFigureEqual:
    """Tests for :func:`assert_figure_equal`."""

    def test_hash_identical_passes(
        self, tiny_png: pathlib.Path, tiny_png_copy: pathlib.Path
    ) -> None:
        """Byte-identical files must pass hash comparison."""
        assert_figure_equal(tiny_png, tiny_png_copy, method="hash")

    def test_hash_different_fails(
        self, tiny_png: pathlib.Path, tiny_png_different: pathlib.Path
    ) -> None:
        """Files with different content must fail hash comparison."""
        with pytest.raises(AssertionError, match="[Hh]ash"):
            assert_figure_equal(tiny_png, tiny_png_different, method="hash")

    def test_pixel_identical_passes(
        self, tiny_png: pathlib.Path, tiny_png_copy: pathlib.Path
    ) -> None:
        assert_figure_equal(tiny_png, tiny_png_copy, method="pixel", pixel_rms_tol=0.0)

    def test_pixel_within_tolerance_passes(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Images that differ by a few pixel values must pass with sufficient tolerance."""
        pytest.importorskip("PIL")
        from PIL import Image  # type: ignore[import]

        ref = Image.new("RGB", (20, 20), color=(100, 100, 100))
        act_arr = np.array(ref, dtype=np.uint8)
        act_arr[:3, :3] = [103, 103, 103]  # tiny patch, RMS << 2.0
        act_img = Image.fromarray(act_arr)

        ref_path = tmp_path / "ref.png"
        act_path = tmp_path / "act.png"
        ref.save(str(ref_path))
        act_img.save(str(act_path))

        assert_figure_equal(act_path, ref_path, method="pixel", pixel_rms_tol=2.0)

    def test_pixel_beyond_tolerance_fails(
        self, tiny_png: pathlib.Path, tiny_png_different: pathlib.Path
    ) -> None:
        """A very different image must fail pixel comparison at tight tolerance."""
        with pytest.raises(AssertionError, match="RMS"):
            assert_figure_equal(
                tiny_png, tiny_png_different, method="pixel", pixel_rms_tol=0.5
            )

    def test_stats_identical_passes(
        self, tiny_png: pathlib.Path, tiny_png_copy: pathlib.Path
    ) -> None:
        assert_figure_equal(tiny_png, tiny_png_copy, method="stats", pixel_rms_tol=0.0)

    def test_stats_different_fails(
        self, tiny_png: pathlib.Path, tiny_png_different: pathlib.Path
    ) -> None:
        with pytest.raises(AssertionError):
            assert_figure_equal(
                tiny_png, tiny_png_different, method="stats", pixel_rms_tol=0.5
            )

    def test_nonexistent_file_raises_fnf(
        self, tmp_path: pathlib.Path, tiny_png: pathlib.Path
    ) -> None:
        ghost = tmp_path / "ghost.png"
        with pytest.raises(FileNotFoundError):
            assert_figure_equal(ghost, tiny_png, method="hash")

    def test_invalid_method_raises_value_error(
        self, tiny_png: pathlib.Path
    ) -> None:
        with pytest.raises(ValueError, match="method"):
            assert_figure_equal(tiny_png, tiny_png, method="bad_method")  # type: ignore[arg-type]
