"""Backward-compatibility shim → ai_productivity.visualization."""
from ai_productivity.visualization.figures import (
    ai_coefficient_comparison,
    ai_tfp_scatter,
    ai_tfp_trend,
    missingness_profile,
)
__all__ = ["ai_tfp_scatter", "ai_tfp_trend", "ai_coefficient_comparison", "missingness_profile"]
