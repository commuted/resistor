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

# Run the CLI against a stock list
resistor 1580 --stock 1k,470,120,2k2
```

## Architecture

The codebase is small with two main modules under `src/resistor/`:

- **solver.py** — Core computation in pure Python. Rows are plain tuples: `(lo, nominal, hi)` for the base table, `(lo, nominal, hi, idx1, idx2)` for combinations, where the indices refer to the base table. `iter_series_rows` / `iter_parallel_rows` are generators (`create_series_table` / `create_parallel_table` are the list-returning wrappers kept for callers that reuse a table), so a wide search costs O(N) memory, not O(N²). `find_best_resistor_config` streams candidates through `heapq.nsmallest` and filters by `configs` *before* ranking; `find_bracketing_singles` returns the below/exact/above single resistors for a target, and both build their result dicts through `_make_result`.

  Scoring (`_make_scorer`): a candidate covering the target scores `|target - nominal| / (hi - lo)` (0.0 = dead centre, always < `_MISS_PENALTY` = 1.0); a candidate that misses scores `1 + miss / target`. The sort key then prefers covering candidates, fewer parts, and better centring in that order (misses: smallest miss, then fewer parts). Combinations where one resistor alone covers the target are skipped unless `allow_dominated=True`.

- **cli.py** — Argparse-based CLI entry point (`resistor` command). `main(argv=None)` so tests can drive it. Output is grouped by part count, so the two are never ranked against each other: "One resistor" comes from `find_bracketing_singles` (below/exact/above, labelled by `position`, so `-n` does not apply), "Two resistors" from a `find_best_resistor_config` call with `-n` results. `print_result(label, item, target)` renders a row, where `label` is either `#<rank>` or the bracket position. Handles resistance parsing (`4.7k`, `4k7`, `470R`, `2M2`), `--stock` lists (inline or `@file`), argument validation via `parser.error`, result formatting, and the "no configuration covers the target" warning on stderr.

The public API is re-exported from `__init__.py`: `solve` (convenience wrapper), `find_best_resistor_config`, `build_base_table`, `create_table`, `create_series_table`, `create_parallel_table`, `iter_series_rows`, `iter_parallel_rows`, `e_decade_table`, `ALL_CONFIGS`.

## Key Details

- Python >=3.10 required. No runtime dependencies (pure standard library).
- Build system: setuptools with `src/` layout. Config in `pyproject.toml`.
- Tests use pytest with classes. The `tables` fixture in `TestFindBestResistorConfig` creates E96/6-decade tables shared across test methods. `tests/test_regressions.py` covers the 0.3.0 bug fixes (dominated combinations, ranking, config filtering, input validation, stock lists, decade coverage, decade-scaling exactness, streaming).
- E-series values: E6/E12/E24 come from the `_IEC_E_VALUES` table (the formula diverges there); E48/E96/E192 are computed and re-rounded with `_round_sig`, which goes through the decimal repr so scaled decades stay exact.
- CI publishes to PyPI via GitHub Actions on release.
