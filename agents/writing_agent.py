"""Backward-compatibility shim → ai_productivity.reporting."""
from ai_productivity.reporting.narrative import write_falsification_results, write_results
__all__ = ["write_results", "write_falsification_results"]
