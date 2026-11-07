"""Resistor: Find optimal resistor configurations using E-series standards."""

from .solver import (
    ALL_CONFIGS,
    build_base_table,
    create_parallel_table,
    create_series_table,
    create_table,
    e_decade_table,
    find_best_resistor_config,
    find_bracketing_singles,
    iter_parallel_rows,
    iter_series_rows,
    solve,
)

__version__ = "0.3.0"
__all__ = [
    "solve",
    "find_best_resistor_config",
    "find_bracketing_singles",
    "build_base_table",
    "create_table",
    "create_series_table",
    "create_parallel_table",
    "iter_series_rows",
    "iter_parallel_rows",
    "e_decade_table",
    "ALL_CONFIGS",
]
