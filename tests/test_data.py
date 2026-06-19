"""
Tests for the data layer: loaders, validators, cleaning.

Sprint 2 milestone: the data module tests pass without touching the real CSV.
We use a small in-memory DataFrame so tests are fast and hermetic.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai_productivity.data.loaders import drop_aggregate_entities, load_panel
from ai_productivity.data.validators import (
    REQUIRED_COLUMNS,
    report_has_blockers,
    save_validation_report,
    validate_data,
)
from ai_productivity.data.cleaning import sample_selection_summary
from ai_productivity.exceptions import DataValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_panel_csv(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "country": ["Albania", "Albania", "Brazil", "Brazil"],
        "year":    [2015, 2016, 2015, 2016],
        "gdp_pc":  [4000.0, 4200.0, 8000.0, 8200.0],
        "ln_gdp":  [np.log(4000.0), np.log(4200.0), np.log(8000.0), np.log(8200.0)],
        "ln_ai":   [-0.5, -0.3, 0.1, 0.2],
        "ln_tfp":  [1.0, 1.1, 1.3, 1.4],
        "ln_hc":   [1.0, 1.0, 1.2, 1.2],
        "AI_index": [0.6, 0.7, 1.1, 1.2],
    })
    path = tmp_path / "panel_clean.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def panel_with_aggregates() -> pd.DataFrame:
    return pd.DataFrame({
        "country": ["Albania", "World", "Brazil", "High income", "Kosovo"],
        "year":    [2015, 2015, 2015, 2015, 2015],
        "ln_ai":   [0.1, 0.5, 0.2, 0.4, 0.3],
    })


@pytest.fixture
def ai_panel() -> pd.DataFrame:
    """Panel with some missing AI data for sample-split tests.

    Albania: 2 rows with ln_ai, 1 missing (2015)
    Brazil:  3 rows with ln_ai, 0 missing
    Chad:    3 rows missing ln_ai
    → in_sample = 5 rows, out_of_sample = 4 rows
    """
    return pd.DataFrame({
        "country": ["Albania"] * 3 + ["Brazil"] * 3 + ["Chad"] * 3,
        "year":    [2014, 2015, 2016] * 3,
        "ln_ai":   [0.1, np.nan, 0.3, 0.4, 0.5, 0.6, np.nan, np.nan, np.nan],
        "ln_gdp":  [8.0, 8.1, 8.2, 9.0, 9.1, 9.2, 6.0, 6.1, 6.2],
        "ln_hc":   [1.0, 1.0, 1.0, 1.2, 1.2, 1.2, 0.8, 0.8, 0.8],
    })


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

class TestLoadPanel:
    def test_loads_csv_and_sorts(self, minimal_panel_csv: Path):
        df = load_panel(minimal_panel_csv)
        assert "country" in df.columns
        pairs = list(zip(df["country"], df["year"]))
        assert pairs == sorted(pairs)

    def test_raises_on_missing_file(self, tmp_path: Path):
        with pytest.raises(DataValidationError, match="not found"):
            load_panel(tmp_path / "nonexistent.csv")

    def test_returns_dataframe(self, minimal_panel_csv: Path):
        df = load_panel(minimal_panel_csv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 4


class TestDropAggregateEntities:
    def test_removes_world_and_high_income(self, panel_with_aggregates: pd.DataFrame):
        result = drop_aggregate_entities(panel_with_aggregates)
        assert "World" not in result["country"].values
        assert "High income" not in result["country"].values

    def test_removes_non_sovereign(self, panel_with_aggregates: pd.DataFrame):
        result = drop_aggregate_entities(panel_with_aggregates)
        assert "Kosovo" not in result["country"].values

    def test_keeps_real_countries(self, panel_with_aggregates: pd.DataFrame):
        result = drop_aggregate_entities(panel_with_aggregates)
        assert set(result["country"].values) == {"Albania", "Brazil"}

    def test_no_country_column_returns_unchanged(self):
        df = pd.DataFrame({"value": [1, 2, 3]})
        result = drop_aggregate_entities(df)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------

class TestValidateData:
    def test_valid_panel_has_no_blockers(self, minimal_panel_csv: Path):
        report = validate_data(minimal_panel_csv)
        assert not report_has_blockers(report)

    def test_missing_columns_flagged(self, tmp_path: Path):
        df = pd.DataFrame({"country": ["A"], "year": [2015], "ln_gdp": [8.0], "ln_ai": [0.1]})
        path = tmp_path / "bad.csv"
        df.to_csv(path, index=False)
        report = validate_data(path)
        assert "ln_tfp" in report["missing_columns"]
        assert "ln_hc" in report["missing_columns"]
        assert report_has_blockers(report)

    def test_duplicate_rows_flagged(self, tmp_path: Path):
        df = pd.DataFrame({
            "country": ["A", "A"], "year": [2015, 2015],
            "ln_gdp": [8.0, 8.0], "ln_ai": [0.1, 0.1],
            "ln_tfp": [1.0, 1.0], "ln_hc": [1.0, 1.0],
        })
        path = tmp_path / "dup.csv"
        df.to_csv(path, index=False)
        report = validate_data(path)
        assert report["duplicate_country_year"] == 1
        assert report_has_blockers(report)

    def test_coverage_counts(self, minimal_panel_csv: Path):
        report = validate_data(minimal_panel_csv)
        assert report["coverage"]["countries"] == 2
        assert report["coverage"]["years"] == 2
        assert report["coverage"]["rows"] == 4


class TestSaveValidationReport:
    def test_writes_valid_json(self, minimal_panel_csv: Path, tmp_path: Path):
        report = validate_data(minimal_panel_csv)
        out = tmp_path / "report.json"
        save_validation_report(report, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert "coverage" in loaded
        assert loaded["coverage"]["rows"] == 4


# ---------------------------------------------------------------------------
# cleaning
# ---------------------------------------------------------------------------

class TestSampleSelectionSummary:
    def test_returns_dataframe_with_expected_columns(self, ai_panel: pd.DataFrame):
        result = sample_selection_summary(ai_panel)
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) >= {"variable", "in_sample_mean", "out_of_sample_mean"}

    def test_attrs_carry_counts(self, ai_panel: pd.DataFrame):
        result = sample_selection_summary(ai_panel)
        assert "in_sample_rows" in result.attrs
        assert "out_of_sample_rows" in result.attrs
        # Albania: 1 missing, Chad: 3 missing → 4 out-of-sample rows
        assert result.attrs["out_of_sample_rows"] == 4

    def test_in_vs_out_split_sums_to_total(self, ai_panel: pd.DataFrame):
        result = sample_selection_summary(ai_panel)
        total = result.attrs["in_sample_rows"] + result.attrs["out_of_sample_rows"]
        assert total == 9  # 3 countries × 3 years
