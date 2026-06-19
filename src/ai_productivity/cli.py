"""
Command-line interface for the AI and Productivity pipeline.

Entry point: ``ai-productivity`` (registered in pyproject.toml).

Commands
--------
ai-productivity --version
    Print version and exit.

ai-productivity doctor
    Verify environment before running the pipeline.

ai-productivity run [OPTIONS]
    Execute the full analysis pipeline:
    validate → load → econometrics → tables → figures → narratives.

Examples
--------
    $ uv run ai-productivity --version
    AI and Productivity 0.1.0

    $ uv run ai-productivity doctor
    ✔ Ready

    $ uv run ai-productivity run
    ════════════════════════════════════════
     AI and Productivity 0.1.0
    ════════════════════════════════════════
    ✔ Validation passed (193 countries, 15 years, 2 895 rows)
    ✔ Robustness suite   (4 models)
    ✔ Sensitivity suite  (4 models)
    ✔ Falsification suite (4 models)
    ✔ Tables written  → tables/
    ✔ Figures written → figures/
    ✔ Narratives written → paper/sections/
    ════════════════════════════════════════
     Pipeline complete in 18.3 s
    ════════════════════════════════════════
"""

from __future__ import annotations

import importlib.metadata
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from ai_productivity import __version__

app = typer.Typer(
    name="ai-productivity",
    help="AI and Productivity — panel econometrics research pipeline.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# --version callback
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"AI and Productivity {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """AI and Productivity pipeline CLI."""


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _check(label: str, ok: bool, detail: str = "") -> bool:
    icon = Text("✔", style="bold green") if ok else Text("✘", style="bold red")
    line = f"  {label}"
    if detail:
        line += f"  ({detail})"
    console.print(icon, line)
    return ok


def _count_rows(path: Path) -> int | None:
    try:
        with path.open(encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return None


# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------

_REQUIRED_PACKAGES = ["pandas", "numpy", "statsmodels", "linearmodels", "matplotlib", "scipy"]
_DATA_FILES = [
    Path("data/processed/panel_clean.csv"),
    Path("data/raw/wdi.csv"),
    Path("data/raw/pwt.csv"),
    Path("data/raw/ai_proxy.csv"),
]
_OUTPUT_DIRS = [Path("tables"), Path("figures"), Path("outputs")]


@app.command()
def doctor() -> None:
    """Verify that the environment is ready to run the pipeline."""
    console.print("\n[bold]AI and Productivity — environment check[/bold]\n")

    all_ok = True

    py_version = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    all_ok &= _check(f"Python {py_version}", py_ok, "" if py_ok else "need ≥ 3.10")

    for pkg in _REQUIRED_PACKAGES:
        try:
            ver = importlib.metadata.version(pkg)
            all_ok &= _check(f"{pkg} {ver}", True)
        except importlib.metadata.PackageNotFoundError:
            all_ok &= _check(pkg, False, "not installed — run: uv pip install -e .")

    console.print()
    console.print("  [dim]Data files[/dim]")
    for path in _DATA_FILES:
        if path.exists():
            rows = _count_rows(path)
            detail = f"{rows:,} rows" if rows is not None else "found"
            all_ok &= _check(str(path), True, detail)
        else:
            all_ok &= _check(str(path), False, "missing — run scripts/01_download_data.py")

    console.print()
    console.print("  [dim]Output directories[/dim]")
    for out_dir in _OUTPUT_DIRS:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            all_ok &= _check(str(out_dir) + "/", True, "writable")
        except OSError as exc:
            all_ok &= _check(str(out_dir) + "/", False, str(exc))

    console.print()
    if all_ok:
        console.print("[bold green]✔ Ready[/bold green]\n")
    else:
        console.print("[bold red]✘ Some checks failed.[/bold red]\n")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

@app.command()
def run(
    data_path: Path = typer.Option(
        Path("data/processed/panel_clean.csv"),
        "--data-path", "-d",
        help="Path to the processed panel CSV.",
        show_default=True,
    ),
    tables_dir: Path = typer.Option(
        Path("tables"),
        "--tables-dir",
        help="Output directory for tables.",
        show_default=True,
    ),
    figures_dir: Path = typer.Option(
        Path("figures"),
        "--figures-dir",
        help="Output directory for figures.",
        show_default=True,
    ),
    paper_dir: Path = typer.Option(
        Path("paper/sections"),
        "--paper-dir",
        help="Output directory for auto-generated LaTeX narrative.",
        show_default=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable DEBUG-level logging.",
    ),
) -> None:
    """Run the full analysis pipeline.

    Executes in order: validate → load → econometrics (12 models) →
    tables → figures → LaTeX narratives.

    On success, every table, figure, and narrative section is regenerated.
    """
    # Lazy import keeps CLI startup fast even when heavy deps are installed.
    from ai_productivity.pipeline import run as _run
    from ai_productivity.exceptions import AIProdError
    from ai_productivity.logging import configure_logging
    import logging

    configure_logging(level=logging.DEBUG if verbose else logging.INFO)

    console.print()
    console.rule(f"[bold]AI and Productivity {__version__}[/bold]")
    console.print()

    if not data_path.exists():
        console.print(f"[bold red]✘ Data file not found:[/bold red] {data_path}")
        console.print("  Run [bold]scripts/02_clean_data.py[/bold] to generate it, or check --data-path.")
        raise typer.Exit(code=1)

    t0 = time.perf_counter()

    try:
        _run(
            data_path=data_path,
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            paper_dir=paper_dir,
            verbose=verbose,
        )
    except AIProdError as exc:
        console.print()
        console.print(f"[bold red]✘ Pipeline error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print()
        console.print(f"[bold red]✘ Unexpected error:[/bold red] {exc}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(code=1)

    elapsed = time.perf_counter() - t0

    console.print()
    console.rule("[bold green]Pipeline complete[/bold green]")
    console.print()

    # Summary of outputs
    _output_summary(tables_dir, figures_dir, paper_dir, elapsed)


def _output_summary(
    tables_dir: Path,
    figures_dir: Path,
    paper_dir: Path,
    elapsed: float,
) -> None:
    """Print a concise summary of what was written."""
    def _count_files(d: Path, suffix: str) -> int:
        return len(list(d.glob(f"*{suffix}"))) if d.exists() else 0

    tables_csv  = _count_files(tables_dir, ".csv")
    tables_tex  = _count_files(tables_dir, ".tex")
    tables_txt  = _count_files(tables_dir, ".txt")
    figures_png = _count_files(figures_dir, ".png")
    paper_tex   = _count_files(paper_dir, ".tex")

    console.print(f"  [dim]tables/[/dim]    {tables_txt} model summaries · {tables_csv} CSV · {tables_tex} LaTeX")
    console.print(f"  [dim]figures/[/dim]   {figures_png} PNG")
    console.print(f"  [dim]{paper_dir}/[/dim]   {paper_tex} LaTeX narrative(s)")
    console.print()
    console.print(f"  Completed in [bold]{elapsed:.1f} s[/bold]")
    console.print()
