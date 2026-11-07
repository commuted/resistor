# resistor

Find optimal resistor configurations for a target resistance using E-series standards.

Given a target resistance, this tool finds the best single resistor or two-resistor combination (series or parallel) from the E-series standard values — or from a list of parts you have in stock — ranked by how well the tolerance envelope contains the target.

## Installation

```bash
pip install resistor
```

Or install from source:

```bash
git clone https://github.com/commuted/resistor.git
cd resistor
pip install -e .
```

## Usage

### Command Line

```bash
# Find configurations for 1580 ohms
resistor 1580

# Supports k (kilo), M (mega) and R (ohms), in either notation
resistor 4.7k
resistor 4k7
resistor 2.2M
resistor 470R

# Show more results (per group: one-resistor and two-resistor)
resistor 1580 -n 10

# Use different E-series (E24 instead of E96)
resistor 1580 -e 24

# Cover more decades (default 7: 1 ohm to 9.76M)
resistor 33M -d 8

# Use 5% tolerance resistors
resistor 1580 -t 5

# Only show single/series/parallel results
resistor 1580 --single-only
resistor 1580 --series-only
resistor 1580 --parallel-only

# Only combine parts you actually have
resistor 1580 --stock 1k,470,120,2k2
resistor 1580 --stock @junkbox.txt

# Also show combinations where one resistor alone already covers the target
resistor 1580 --allow-dominated
```

A stock file holds one or more values per line, with `#` comments:

```
# junk box
1k  470  120
2k2   # from the last order
```

### Python API

```python
from resistor import solve

# One call: builds the tables, streams the combinations, ranks the results
for r in solve(1580, es=96, decades=7, tolerance=0.01, n=5):
    print(f"{r['config']}: {r['resistors']} = {r['nominal']}Ω")

# Restrict to what you have in stock, or to one configuration kind
solve(1580, values=[120, 470, 1000, 2200], n=5)
solve(1580, configs=["parallel"], n=5)
```

For the bracketing single resistors the CLI shows, use
`find_bracketing_singles`; each result carries a `position` of `"below"`,
`"exact"` or `"above"`:

```python
from resistor import build_base_table, find_bracketing_singles

base_table = build_base_table(es=96, decades=7)
for r in find_bracketing_singles(1580, base_table):
    print(r["position"], r["nominal"])      # below 1540.0 / exact 1580.0 / above 1620.0
```

For repeated queries against the same table, build it once and call the solver
directly. The combination rows are generators, so a wide search costs memory
proportional to the base table rather than to its square:

```python
from resistor import (
    build_base_table,
    find_best_resistor_config,
    iter_parallel_rows,
    iter_series_rows,
)

base_table = build_base_table(es=96, decades=7, tolerance=0.01)

results = find_best_resistor_config(
    target=1580,
    base_table=base_table,
    series_table=iter_series_rows(base_table),
    parallel_table=iter_parallel_rows(base_table),
    n=5,
)
```

`create_series_table` / `create_parallel_table` still return the fully
materialized lists if you need to reuse them across queries.

## How It Works

1. Generates E-series values (default E96) across multiple decades with tolerance bounds, or uses your `--stock` list
2. Computes all series combinations: R_total = R1 + R2
3. Computes all parallel combinations: R_total = (R1 × R2)/(R1 + R2)
4. Scores each configuration by how well the tolerance envelope contains the target
5. Returns the top-n results

### Output groups

Results are ranked **separately for each part count**, so a one-resistor option
never competes with a two-resistor one:

```
$ resistor 1580 -n 2

Target: 1580 ohms
E-series: E96, Tolerance: ±1.0%

One resistor
------------
below: SINGLE 1.54k
    Nominal: 1540 ohms (-2.5316%)
    Range:   [1524.6, 1555.4]  (-1%/+1%)  <-- does NOT cover target

exact: SINGLE 1.58k
    Nominal: 1580 ohms (+0.0000%)
    Range:   [1564.2, 1595.8]  (-1%/+1%)

above: SINGLE 1.62k
    Nominal: 1620 ohms (+2.5316%)
    Range:   [1603.8, 1636.2]  (-1%/+1%)

Two resistors
-------------
#1: SERIES 340 + 1.24k
    Nominal: 1580 ohms (+0.0000%)
    Range:   [1564.2, 1595.8]  (-1%/+1%)

#2: SERIES 649 + 931
    Nominal: 1580 ohms (+0.0000%)
    Range:   [1564.2, 1595.8]  (-1%/+1%)
```

The **one-resistor group brackets the target**: the nearest standard value
below it, the exact value if the series has one, and the nearest value above —
three rows on an exact match, two otherwise (one at the ends of the range).
Anything further out is simply further from the target, so `-n` does not apply
here; it sets the number of **two-resistor** results.

`--single-only` prints just the one-resistor group; `--series-only` /
`--parallel-only` print just the two-resistor group, restricted to that kind.

### Scoring and ranking

In the two-resistor group, ranking starts at the centre and radiates outward:
the result closest to the target comes first, and `|error|` grows monotonically
down the list, so asking for more results only ever adds wider options. The
one-resistor group is ordered by value instead, low to high.

A configuration whose tolerance envelope **covers** the target scores
`|target − nominal| / (hi − lo)`: 0.0 is a dead-centre match, and anything
covering stays below 1.0. A configuration that **misses** the target scores
`1 + miss / target`, so every covering option ranks above every missing one.

Within those two classes:

- **Covering**: fewer parts first, then the best centring. This matters for the
  flat list the Python API returns; the CLI groups by part count instead.
- **Missing**: smallest miss first, then fewer parts. Every such row is marked
  `<-- does NOT cover target`, and if *nothing* covers the target a warning
  explains how to widen the search.

Two-resistor combinations in which **one resistor already covers the target on
its own** are dropped: "1.58k + 1" for a 1580 target is strictly worse than the
1.58k alone (two parts, two tolerance stacks, no benefit). Pass
`--allow-dominated` to see them anyway.

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
pytest --cov=resistor --cov-report=term-missing
```

## License

MIT
