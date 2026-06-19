"""
AI and Productivity — panel econometrics research pipeline.

Investigates the relationship between AI adoption and total factor productivity
across a cross-national panel, 2010–2024.
"""

__version__ = "0.1.0"
__author__ = "Ab"
__email__ = "abrhamgs3@gmail.com"

from ai_productivity.exceptions import (
    AIProdError,
    DataValidationError,
    MergeError,
    ModelSpecificationError,
    PipelineError,
)

__all__ = [
    "__version__",
    "AIProdError",
    "DataValidationError",
    "MergeError",
    "ModelSpecificationError",
    "PipelineError",
]
