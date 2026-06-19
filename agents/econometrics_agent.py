"""Backward-compatibility shim → ai_productivity.econometrics."""
from ai_productivity.econometrics.panel import (
    run_falsification_suite,
    run_growth_model,
    run_robustness_suite,
    run_sensitivity_suite,
    run_tfp_model,
)
__all__ = [
    "run_tfp_model", "run_growth_model",
    "run_robustness_suite", "run_sensitivity_suite", "run_falsification_suite",
]
