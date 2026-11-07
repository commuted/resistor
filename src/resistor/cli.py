"""Command-line interface for resistor."""

import argparse
import math
import re
import sys

from .solver import (
    ALL_CONFIGS,
    build_base_table,
    find_best_resistor_config,
    find_bracketing_singles,
    iter_parallel_rows,
    iter_series_rows,
)

MAX_DECADES = 10

ISSUES_URL = "https://github.com/commuted/resistor/issues"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resistor",
        description="Find optimal resistor configurations for a target resistance value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  resistor 1580                        # Find configs for 1580 ohms
  resistor 4.7k                        # Find configs for 4700 ohms
  resistor 4k7                         # Same, EIA notation
  resistor 2.2M -n 10                  # Find top 10 configs for 2.2M ohms
  resistor 100 --tolerance 5           # Use 5% tolerance resistors
  resistor 1580 --stock 1k,470,120,2k2 # Only combine parts you have
  resistor 1580 --stock @parts.txt     # Stock list from a file

Report bugs at: {ISSUES_URL}
        """.format(ISSUES_URL=ISSUES_URL)
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target resistance (supports k/K for kilo, M for mega, R for ohms, "
             "in either 4.7k or 4k7 form)"
    )
    parser.add_argument(
        "-n", "--num-results",
        type=int,
        default=5,
        help="Number of two-resistor results to show (default: 5); the "
             "one-resistor group always shows the bracketing values"
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
        default=7,
        help=f"Number of decades to cover (default: 7, covers 1 ohm to 9.76M, "
             f"range 1-{MAX_DECADES})"
    )
    parser.add_argument(
        "-t", "--tolerance",
        type=float,
        default=1.0,
        help="Resistor tolerance in percent (default: 1.0)"
    )
    parser.add_argument(
        "--stock",
        type=str,
        default=None,
        help="Comma-separated list of resistor values on hand (or @file with one "
             "value per line). Overrides --e-series/--decades."
    )
    parser.add_argument(
        "--allow-dominated",
        action="store_true",
        help="Also show combinations where one resistor alone already covers the "
             "target (e.g. '1.58k + 1' for 1580); hidden by default as they are "
             "strictly worse than that single resistor"
    )
    only = parser.add_mutually_exclusive_group()
    only.add_argument(
        "--single-only",
        dest="only", action="store_const", const="single",
        help="Only show single resistor matches"
    )
    only.add_argument(
        "--series-only",
        dest="only", action="store_const", const="series",
        help="Only show series combinations"
    )
    only.add_argument(
        "--parallel-only",
        dest="only", action="store_const", const="parallel",
        help="Only show parallel combinations"
    )
    parser.set_defaults(only=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate target
    target = parse_resistance(args.target)
    if target is None:
        parser.error(f"invalid resistance value '{args.target}'")
    if target <= 0:
        parser.error(f"target resistance must be greater than zero, got {target:g}")

    # Validate the rest
    if args.num_results < 1:
        parser.error(f"--num-results must be at least 1, got {args.num_results}")
    if not 1 <= args.decades <= MAX_DECADES:
        parser.error(f"--decades must be between 1 and {MAX_DECADES}, got {args.decades}")
    if not 0 <= args.tolerance < 100:
        parser.error(f"--tolerance must be at least 0 and below 100 percent, got {args.tolerance:g}")

    stock = None
    if args.stock is not None:
        stock = parse_stock(args.stock)
        if not stock:
            parser.error(f"no usable resistor values in --stock '{args.stock}'")

    tolerance = args.tolerance / 100.0
    configs = ALL_CONFIGS if args.only is None else (args.only,)

    base_table = build_base_table(
        es=args.e_series,
        precision=3,
        decades=args.decades,
        tolerance=tolerance,
        values=stock,
    )

    # One group per part count: one-resistor options never compete with
    # two-resistor ones.
    one_part = [c for c in configs if c == "single"]
    two_part = [c for c in configs if c in ("series", "parallel")]

    groups = []
    if one_part:
        # The only single resistors worth seeing are the ones bracketing the
        # target: nearest below, the exact value if the series has one, nearest
        # above. Two rows normally, three on an exact match.
        groups.append(("One resistor", find_bracketing_singles(target, base_table)))
    if two_part:
        label = "Two resistors"
        if len(two_part) == 1:
            label += f" ({two_part[0]} only)"
        # Combination rows are streamed, so the ones we do not need are never built.
        groups.append((
            label,
            find_best_resistor_config(
                target,
                base_table,
                iter_series_rows(base_table) if "series" in two_part else None,
                iter_parallel_rows(base_table) if "parallel" in two_part else None,
                n=args.num_results,
                configs=two_part,
                allow_dominated=args.allow_dominated,
            ),
        ))

    # Display results
    print(f"\nTarget: {target:.6g} ohms")
    if stock is None:
        print(f"E-series: E{args.e_series}, Tolerance: ±{args.tolerance}%")
    else:
        print(f"Stock: {len(stock)} values, Tolerance: ±{args.tolerance}%")

    results = [item for _label, items in groups for item in items]
    if not results:
        print("\nNo matching configurations found.")
        sys.exit(1)

    for label, items in groups:
        print(f"\n{label}")
        print("-" * len(label))
        if not items:
            print("(none available)\n")
            continue
        for rank, item in enumerate(items, 1):
            # Bracketing singles are labelled by position, not ranked.
            print_result(item.get("position") or f"#{rank}", item, target)

    if not any(r["lo"] <= target <= r["hi"] for r in results):
        sys.stdout.flush()  # keep the stderr warning after the results when piped
        warn_uncovered(target, base_table, configs, stock is not None, args.decades)


def print_result(label: str, item: dict, target: float) -> None:
    """Print one configuration, tagged with its rank or bracket position."""
    joiner = " || " if item["config"] == "parallel" else " + "
    resistors_str = joiner.join(format_resistance(r) for r in item["resistors"])
    error_pct = (item["nominal"] - target) / target * 100
    covered = item["lo"] <= target <= item["hi"]

    print(f"{label}: {item['config'].upper()} {resistors_str}")
    print(f"    Nominal: {item['nominal']:.6g} ohms ({error_pct:+.4f}%)")
    print(f"    Range:   [{item['lo']:.6g}, {item['hi']:.6g}]"
          f"  (-{item['lower_tol_pct']:g}%/+{item['upper_tol_pct']:g}%)"
          f"{'' if covered else '  <-- does NOT cover target'}")
    print()


def warn_uncovered(target, base_table, configs, using_stock, decades) -> None:
    """Warn when no returned configuration's envelope contains the target."""
    noms = [row[1] for row in base_table]
    lows, highs = [], []
    if "single" in configs:
        lows.append(min(noms))
        highs.append(max(noms))
    if "series" in configs:
        lows.append(2 * min(noms))
        highs.append(2 * max(noms))
    if "parallel" in configs:
        lows.append(min(noms) / 2)
        highs.append(max(noms) / 2)
    reach_lo, reach_hi = min(lows), max(highs)

    print("Warning: no configuration's tolerance envelope covers the target; "
          "the results above are the closest misses.", file=sys.stderr)
    if target > reach_hi or target < reach_lo:
        print(f"         The target is outside the reachable range "
              f"[{reach_lo:.6g}, {reach_hi:.6g}] ohms.", file=sys.stderr)
        if using_stock:
            print("         Add more values to --stock.", file=sys.stderr)
        elif target > reach_hi and decades < MAX_DECADES:
            print(f"         Try -d {min(MAX_DECADES, decades + 1 + int(math.log10(target / reach_hi)))}"
                  f" to generate higher decades.", file=sys.stderr)
    elif using_stock:
        print("         Add more values to --stock, or loosen the tolerance (-t).",
              file=sys.stderr)
    else:
        print("         Try a finer E-series (-e 192) or a looser tolerance (-t).",
              file=sys.stderr)


# 4k7 / 4.7k / 470R / 2M2 — number, unit, optional fractional digits after the unit
_VALUE_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+))([kmr])(\d*)$", re.IGNORECASE)

_MULTIPLIERS = {
    'k': 1e3,
    'm': 1e6,
    'r': 1.0,  # Sometimes used for ohms
}


def parse_resistance(value: str) -> float | None:
    """Parse a resistance value with an optional k/M/R suffix or infix.

    Accepts "1000", "4.7k", "4k7", "2.2M", "2M2", "470R" and "4R7".
    Returns None for anything unparseable, infinite or NaN.
    """
    if value is None:
        return None
    text = value.strip().replace(" ", "")
    if not text:
        return None

    match = _VALUE_RE.match(text)
    if match:
        whole, suffix, frac = match.groups()
        if frac:
            if "." in whole:
                return None  # "1.5k5" is not a thing
            number = f"{whole}.{frac}"
        else:
            number = whole
        try:
            parsed = float(number) * _MULTIPLIERS[suffix.lower()]
        except ValueError:
            return None
    else:
        try:
            parsed = float(text)
        except ValueError:
            return None

    return parsed if math.isfinite(parsed) else None


def parse_stock(spec: str) -> list[float]:
    """Parse a stock list: comma/whitespace separated values, or @filename."""
    text = spec.strip()
    if text.startswith("@"):
        path = text[1:]
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            print(f"Error: cannot read stock file '{path}': {exc}", file=sys.stderr)
            sys.exit(1)

    # Strip "#" comments per line before tokenizing.
    text = "\n".join(line.split("#", 1)[0] for line in text.splitlines())

    values = []
    for token in re.split(r"[,\s;]+", text):
        token = token.strip()
        if not token:
            continue
        parsed = parse_resistance(token)
        if parsed is None or parsed <= 0:
            print(f"Error: invalid resistor value in stock list: '{token}'", file=sys.stderr)
            sys.exit(1)
        values.append(parsed)
    return sorted(set(values))


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
