"""
Tests for the exception hierarchy.

Sprint 1 milestone: the first automated test passes.

These tests verify two things:
1. Every custom exception can be raised and caught.
2. The inheritance chain is correct — catching ``AIProdError`` catches all
   domain exceptions (useful for top-level error handling in the CLI).
"""

import pytest

from ai_productivity.exceptions import (
    AIProdError,
    DataValidationError,
    MergeError,
    ModelSpecificationError,
    PipelineError,
)


class TestExceptionHierarchy:
    """All domain exceptions must be subclasses of AIProdError."""

    def test_data_validation_error_is_aiprod_error(self):
        with pytest.raises(AIProdError):
            raise DataValidationError("column 'ln_tfp' missing")

    def test_merge_error_is_aiprod_error(self):
        with pytest.raises(AIProdError):
            raise MergeError("ISO3 code 'XYZ' not found")

    def test_pipeline_error_is_aiprod_error(self):
        with pytest.raises(AIProdError):
            raise PipelineError("panel_clean.csv missing — run 02_clean_data.py first")

    def test_model_specification_error_is_aiprod_error(self):
        with pytest.raises(AIProdError):
            raise ModelSpecificationError("ln_ai is collinear with entity effects")


class TestExceptionMessages:
    """Exception messages should be preserved and readable."""

    def test_data_validation_error_message(self):
        msg = "duplicate (country, year) rows: 3 detected"
        exc = DataValidationError(msg)
        assert str(exc) == msg

    def test_merge_error_message(self):
        msg = "left join produced 42 unexpected duplicate rows"
        exc = MergeError(msg)
        assert str(exc) == msg

    def test_pipeline_error_message(self):
        msg = "step 3 requires step 2 output"
        exc = PipelineError(msg)
        assert str(exc) == msg

    def test_model_specification_error_message(self):
        msg = "formula 'ln_tfp ~ ln_ai + ln_ai' contains duplicate term"
        exc = ModelSpecificationError(msg)
        assert str(exc) == msg


class TestExceptionSpecificity:
    """Each exception should only catch its own type, not siblings."""

    def test_merge_error_not_caught_as_data_validation(self):
        with pytest.raises(MergeError):
            raise MergeError("wrong key")

        # DataValidationError should NOT catch MergeError
        with pytest.raises(MergeError):
            try:
                raise MergeError("wrong key")
            except DataValidationError:
                pass  # this branch must NOT execute

    def test_pipeline_error_not_caught_as_model_specification(self):
        with pytest.raises(PipelineError):
            try:
                raise PipelineError("missing file")
            except ModelSpecificationError:
                pass  # this branch must NOT execute
