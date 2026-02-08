# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

resistor is a Python CLI tool and library for finding optimal resistor configurations using E-series (IEC 60063) standards. Given a target resistance, it finds the best single resistor or two-resistor combination (series or parallel) ranked by how well the tolerance envelope contains the target.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=resistor --cov-report=term-missing

# Run a single test
pytest tests/test_solver.py::TestEDecadeTable::test_e96_first_decade_length

# Run the CLI
resistor 1580
```

## Architecture

The codebase is small with two main modules under `src/resistor/`:

- **solver.py** — Core computation using NumPy. Generates E-series value tables as NumPy arrays with columns `[lo, nominal, hi]` (base table, shape `N×3`) or `[lo, nominal, hi, idx1, idx2]` (combination tables, shape `N²×5`). The scoring function (`get_score` inside `find_best_resistor_config`) returns 0 when target is within tolerance bounds, otherwise normalized distance, with a `1e-10` relative-error tiebreaker.

- **cli.py** — Argparse-based CLI entry point (`resistor` command). Handles resistance parsing (k/M/r suffixes) and result formatting. Delegates all computation to solver.

The public API is re-exported from `__init__.py`: `find_best_resistor_config`, `create_table`, `create_series_table`, `create_parallel_table`, `e_decade_table`.

## Key Details

- Python >=3.10 required. Only runtime dependency is NumPy.
- Build system: setuptools with `src/` layout. Config in `pyproject.toml`.
- Tests use pytest with classes. The `tables` fixture in `TestFindBestResistorConfig` creates E96/6-decade tables shared across test methods.
- CI publishes to PyPI via GitHub Actions on release.
