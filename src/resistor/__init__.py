"""Resistor: Find optimal resistor configurations using E-series standards."""

from .solver import (
    find_best_resistor_config,
    create_table,
    create_series_table,
    create_parallel_table,
    e_decade_table,
)

__version__ = "0.1.0"
__all__ = [
    "find_best_resistor_config",
    "create_table",
    "create_series_table",
    "create_parallel_table",
    "e_decade_table",
]
