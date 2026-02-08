"""Command-line interface for resistor."""

import argparse
import sys

from .solver import (
    find_best_resistor_config,
    create_table,
    create_series_table,
    create_parallel_table,
)


def main():
    parser = argparse.ArgumentParser(
        description="Find optimal resistor configurations for a target resistance value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  resistor 1580              # Find configs for 1580 ohms
  resistor 4.7k              # Find configs for 4700 ohms
  resistor 2.2M -n 10        # Find top 10 configs for 2.2M ohms
  resistor 100 --tolerance 5 # Use 5% tolerance resistors
        """
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target resistance (supports k/K for kilo, M for mega, e.g., 4.7k, 2.2M)"
    )
    parser.add_argument(
        "-n", "--num-results",
        type=int,
        default=5,
        help="Number of results to show (default: 5)"
    )
    parser.add_argument(
        "-e", "--e-series",
        type=int,
        default=96,
        choices=[6, 12, 24, 48, 96, 192],
        help="E-series to use (default: 96)"
    )
    parser.add_argument(
        "-d", "--decades",
        type=int,
        default=6,
        help="Number of decades to cover (default: 6, range 1-1M ohms)"
    )
    parser.add_argument(
        "-t", "--tolerance",
        type=float,
        default=1.0,
        help="Resistor tolerance in percent (default: 1.0)"
    )
    parser.add_argument(
        "--single-only",
        action="store_true",
        help="Only show single resistor matches"
    )
    parser.add_argument(
        "--series-only",
        action="store_true",
        help="Only show series combinations"
    )
    parser.add_argument(
        "--parallel-only",
        action="store_true",
        help="Only show parallel combinations"
    )

    args = parser.parse_args()

    # Parse target value with suffix support
    target = parse_resistance(args.target)
    if target is None:
        print(f"Error: Invalid resistance value '{args.target}'", file=sys.stderr)
        sys.exit(1)

    # Generate tables
    tolerance = args.tolerance / 100.0
    base_table = create_table(
        es=args.e_series,
        precision=3,
        decades=args.decades,
        tolerance=tolerance
    )
    series_table = create_series_table(base_table)
    parallel_table = create_parallel_table(base_table)

    # Find best configurations
    results = find_best_resistor_config(
        target,
        base_table,
        series_table,
        parallel_table,
        n=args.num_results * 3  # Get extra to filter
    )

    # Filter by config type if requested
    if args.single_only:
        results = [r for r in results if r["config"] == "single"]
    elif args.series_only:
        results = [r for r in results if r["config"] == "series"]
    elif args.parallel_only:
        results = [r for r in results if r["config"] == "parallel"]

    results = results[:args.num_results]

    # Display results
    print(f"\nTarget: {target:.6g} ohms")
    print(f"E-series: E{args.e_series}, Tolerance: ±{args.tolerance}%\n")

    if not results:
        print("No matching configurations found.")
        sys.exit(0)

    for rank, item in enumerate(results, 1):
        resistors_str = " + ".join(format_resistance(r) for r in item["resistors"])
        if item["config"] == "parallel":
            resistors_str = " || ".join(format_resistance(r) for r in item["resistors"])

        error_pct = (item["nominal"] - target) / target * 100

        print(f"#{rank}: {item['config'].upper()} {resistors_str}")
        print(f"    Nominal: {item['nominal']:.6g} ohms ({error_pct:+.4f}%)")
        print(f"    Range:   [{item['lo']:.6g}, {item['hi']:.6g}]")
        print()


def parse_resistance(value: str) -> float | None:
    """Parse resistance value with optional k/M suffix."""
    value = value.strip().lower()
    multipliers = {
        'k': 1e3,
        'm': 1e6,
        'r': 1,  # Sometimes used for ohms
    }

    multiplier = 1.0
    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            value = value[:-1]
            multiplier = mult
            break

    try:
        return float(value) * multiplier
    except ValueError:
        return None


def format_resistance(value: float) -> str:
    """Format resistance value with appropriate unit."""
    if value >= 1e6:
        return f"{value/1e6:.3g}M"
    elif value >= 1e3:
        return f"{value/1e3:.3g}k"
    else:
        return f"{value:.3g}"


if __name__ == "__main__":
    main()
