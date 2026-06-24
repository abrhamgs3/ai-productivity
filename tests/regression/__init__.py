"""
tests/regression
================
Regression-testing utilities for the AI & Productivity research pipeline.

This package provides reusable comparison functions that verify future
refactoring does not alter scientific outputs.  Every function raises
``AssertionError`` with a descriptive, diff-style message on failure and
returns ``None`` on success.

Public API
----------
assert_csv_equal        Compare two CSV files within numeric tolerance.
assert_parquet_equal    Compare two Parquet datasets within numeric tolerance.
assert_dataframe_equal  Compare two pandas DataFrames within numeric tolerance.
assert_coefficient_equal
                        Compare one regression coefficient across two models.
assert_latex_equal      Compare two LaTeX strings (whitespace-normalised).
assert_figure_equal     Compare two image files by hash or pixel statistics.
"""
from .helpers import (
    assert_csv_equal,
    assert_dataframe_equal,
    assert_parquet_equal,
    assert_coefficient_equal,
    assert_latex_equal,
    assert_figure_equal,
)

__all__ = [
    "assert_csv_equal",
    "assert_dataframe_equal",
    "assert_parquet_equal",
    "assert_coefficient_equal",
    "assert_latex_equal",
    "assert_figure_equal",
]
