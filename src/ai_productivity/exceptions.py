"""
Domain-specific exception hierarchy for the AI and Productivity pipeline.

Why custom exceptions?
----------------------
Generic ``Exception`` or ``ValueError`` tell the user *something* went wrong.
Domain exceptions tell the user *what* went wrong, in terms they understand:
a merge failed, a model is mis-specified, validation blocked the pipeline.

Hierarchy
---------
AIProdError          ← base; catch this to handle any pipeline error
├── DataValidationError   ← required columns missing, duplicates, non-finite log vars
├── MergeError            ← ISO3 lookup failed, key collision during merge
├── PipelineError         ← step ran out of order, intermediate file missing
└── ModelSpecificationError  ← formula invalid, collinear regressors, insufficient obs
"""


class AIProdError(Exception):
    """Base exception for all AI & Productivity pipeline errors."""


class DataValidationError(AIProdError):
    """Raised when the panel dataset fails schema or quality checks.

    Examples
    --------
    - Required column ``ln_tfp`` is missing.
    - Duplicate (country, year) rows detected.
    - Log-transformed variable contains ``-inf`` or ``NaN``.
    """


class MergeError(AIProdError):
    """Raised when a merge between two data sources cannot be completed safely.

    Examples
    --------
    - An ISO3 country code is not found in the reference lookup.
    - A left-join produces unexpected row duplication.
    - Two sources disagree on a shared key column.
    """


class PipelineError(AIProdError):
    """Raised when a pipeline step is invoked in an invalid state.

    Examples
    --------
    - ``run_regressions()`` called before ``build_panel()`` has written its output.
    - An intermediate file is missing or empty.
    - A step receives an unexpected data schema from the previous step.
    """


class ModelSpecificationError(AIProdError):
    """Raised when an econometric or ML model cannot be estimated as specified.

    Examples
    --------
    - A regressor is perfectly collinear with the fixed effects.
    - The formula string cannot be parsed.
    - The entity-time panel has fewer observations than parameters.
    """
