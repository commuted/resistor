# e-table

Find optimal resistor configurations for a target resistance using E-series standards.

Given a target resistance, this tool finds the best single resistor or two-resistor combination (series or parallel) from the E-series standard values, ranked by how well the tolerance envelope contains the target.

## Installation

```bash
pip install e-table
```

Or install from source:

```bash
git clone https://github.com/commuted/e-table.git
cd e-table
pip install -e .
```

## Usage

### Command Line

```bash
# Find configurations for 1580 ohms
e-table 1580

# Supports k (kilo) and M (mega) suffixes
e-table 4.7k
e-table 2.2M

# Show more results
e-table 1580 -n 10

# Use different E-series (E24 instead of E96)
e-table 1580 -e 24

# Use 5% tolerance resistors
e-table 1580 -t 5

# Only show single/series/parallel results
e-table 1580 --single-only
e-table 1580 --series-only
e-table 1580 --parallel-only
```

### Python API

```python
from e_table import (
    find_best_resistor_config,
    create_table,
    create_series_table,
    create_parallel_table,
)

# Create lookup tables (do once, reuse for multiple queries)
base_table = create_table(es=96, decades=6, tolerance=0.01)
series_table = create_series_table(base_table)
parallel_table = create_parallel_table(base_table)

# Find best configurations for target
results = find_best_resistor_config(
    target=1580,
    base_table=base_table,
    series_table=series_table,
    parallel_table=parallel_table,
    n=5
)

for r in results:
    print(f"{r['config']}: {r['resistors']} = {r['nominal']}Ω")
```

## How It Works

1. Generates E-series values (default E96) across multiple decades with tolerance bounds
2. Computes all series combinations: R_total = R1 + R2
3. Computes all parallel combinations: R_total = (R1 × R2)/(R1 + R2)
4. Scores each configuration by how well the tolerance envelope contains the target
5. Returns top-n results sorted by score

The scoring function returns 0 if the target falls within the tolerance envelope, otherwise returns the normalized distance to the nearest bound. A small tiebreaker based on relative error ensures consistent ordering for equal scores.

## E-Series Standards

The E-series (IEC 60063) defines preferred number values for electronic components:

| Series | Values/Decade | Typical Tolerance |
|--------|--------------|-------------------|
| E6     | 6            | 20%               |
| E12    | 12           | 10%               |
| E24    | 24           | 5%                |
| E48    | 48           | 2%                |
| E96    | 96           | 1%                |
| E192   | 192          | 0.5%              |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=e_table --cov-report=term-missing
```

## License

MIT
