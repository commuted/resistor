"""Core solver for finding optimal resistor configurations."""

import heapq
import math
from collections.abc import Iterable, Iterator, Sequence

# IEC 60063 standard values for E24 and below.
# These diverge from the mathematical 10^(k/es) formula.
_IEC_E_VALUES = {
    6:  [1.0, 1.5, 2.2, 3.3, 4.7, 6.8],
    12: [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    24: [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
         3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1],
}

#: The configuration kinds the solver can return, in preference order.
ALL_CONFIGS = ("single", "series", "parallel")

_CONFIG_RANK = {name: rank for rank, name in enumerate(ALL_CONFIGS)}
_RANK_CONFIG = {rank: name for name, rank in _CONFIG_RANK.items()}

# Any candidate whose tolerance envelope contains the target scores below
# _MISS_PENALTY; any candidate that misses the target scores above it.
_MISS_PENALTY = 1.0


def _round_sig(value: float, sig: int) -> float:
    """Round to `sig` significant figures (no-op for 0 / inf / nan).

    Goes through the decimal repr so the result is the nearest double to the
    rounded decimal, with no scaling fuzz (1.2 * 1e7 would otherwise land on
    11999999.999999998).
    """
    if value == 0.0 or not math.isfinite(value):
        return value
    return float(f"{value:.{sig}g}")


def e_decade_table(es: int = 96, precision: int = 3, decade: int = 1) -> list[float]:
    """Generate one decade of E-series values with correct significant-figure rounding.

    Args:
        es: E-series number (e.g., 96 for E96)
        precision: Number of significant figures
        decade: Decade number (1 = 1-10, 2 = 10-100, etc.)

    Returns:
        List of rounded resistor values for one decade
    """
    scale = 10 ** (decade - 1)

    if es in _IEC_E_VALUES:
        # Standard values carry two significant figures; re-round after scaling
        # so decades above 100 stay exact (0.11e3 * 1e3 == 110.00000000000001).
        sig = max(precision, 2)
        return [_round_sig(v * scale, sig) for v in _IEC_E_VALUES[es]]

    return [_round_sig(10.0 ** (k / es) * scale, precision) for k in range(es)]


def create_table(es: int = 96, precision: int = 3, decades: int = 6, tolerance: float = 0.01) -> list[tuple[float, float, float]]:
    """Create base E-series table with tolerance bounds.

    Args:
        es: E-series number (e.g., 96 for E96)
        precision: Number of significant figures
        decades: Number of decades to generate (1-10, 10-100, etc.)
        tolerance: Tolerance as decimal (0.01 = 1%)

    Returns:
        List of (lo, nominal, hi) tuples
    """
    nominals = []
    for d in range(1, decades + 1):
        nominals.extend(e_decade_table(es=es, precision=precision, decade=d))
    return [(nom * (1 - tolerance), nom, nom * (1 + tolerance)) for nom in nominals]


def build_base_table(
    es: int = 96,
    precision: int = 3,
    decades: int = 7,
    tolerance: float = 0.01,
    values: Iterable[float] | None = None,
) -> list[tuple[float, float, float]]:
    """Build a base table from an E-series, or from an explicit list of values.

    Args:
        es: E-series number, used when `values` is None
        precision: Number of significant figures, used when `values` is None
        decades: Number of decades to generate, used when `values` is None
        tolerance: Tolerance as decimal (0.01 = 1%)
        values: Explicit resistor values (e.g. the parts you have in stock).
            When given, the E-series arguments are ignored.

    Returns:
        List of (lo, nominal, hi) tuples, sorted by nominal
    """
    if values is None:
        return create_table(es=es, precision=precision, decades=decades, tolerance=tolerance)

    nominals = sorted({float(v) for v in values})
    if not nominals:
        raise ValueError("values must contain at least one resistor value")
    for nom in nominals:
        if not math.isfinite(nom) or nom <= 0:
            raise ValueError(f"resistor values must be finite and positive, got {nom!r}")
    return [(nom * (1 - tolerance), nom, nom * (1 + tolerance)) for nom in nominals]


def iter_series_rows(base_table: Sequence[tuple[float, float, float]]) -> Iterator[tuple[float, float, float, int, int]]:
    """Yield every series combination of the base table, without materializing it.

    Yields:
        (lo, nominal, hi, idx1, idx2) tuples with idx1 <= idx2
    """
    n = len(base_table)
    for i in range(n):
        lo_i, nom_i, hi_i = base_table[i]
        for j in range(i, n):
            lo_j, nom_j, hi_j = base_table[j]
            yield (lo_i + lo_j, nom_i + nom_j, hi_i + hi_j, i, j)


def iter_parallel_rows(base_table: Sequence[tuple[float, float, float]]) -> Iterator[tuple[float, float, float, int, int]]:
    """Yield every parallel combination of the base table, without materializing it.

    Yields:
        (lo, nominal, hi, idx1, idx2) tuples with idx1 <= idx2
    """
    n = len(base_table)
    for i in range(n):
        lo_i, nom_i, hi_i = base_table[i]
        for j in range(i, n):
            lo_j, nom_j, hi_j = base_table[j]
            yield (
                (lo_i * lo_j) / (lo_i + lo_j),
                (nom_i * nom_j) / (nom_i + nom_j),
                (hi_i * hi_j) / (hi_i + hi_j),
                i,
                j,
            )


def create_series_table(base_table: list[tuple[float, float, float]]) -> list[tuple[float, float, float, int, int]]:
    """Create all series combinations from base table.

    Args:
        base_table: List of (lo, nominal, hi) tuples

    Returns:
        List of (lo, nominal, hi, idx1, idx2) tuples
    """
    return list(iter_series_rows(base_table))


def create_parallel_table(base_table: list[tuple[float, float, float]]) -> list[tuple[float, float, float, int, int]]:
    """Create all parallel combinations from base table.

    Args:
        base_table: List of (lo, nominal, hi) tuples

    Returns:
        List of (lo, nominal, hi, idx1, idx2) tuples
    """
    return list(iter_parallel_rows(base_table))


def _normalize_configs(configs: Iterable[str] | None) -> set[str]:
    if configs is None:
        return set(ALL_CONFIGS)
    enabled = {str(c).lower() for c in configs}
    unknown = enabled - set(ALL_CONFIGS)
    if unknown:
        raise ValueError(
            f"unknown config type(s) {sorted(unknown)}; expected any of {list(ALL_CONFIGS)}"
        )
    if not enabled:
        raise ValueError("configs must enable at least one of " + str(list(ALL_CONFIGS)))
    return enabled


def _make_scorer(target: float):
    """Build the scoring function for a target (lower score is better).

    A candidate whose tolerance envelope contains the target scores
    `|target - nominal| / (hi - lo)` — the fraction of the envelope's
    half-width the target is off centre, so 0.0 is a dead-centre match and
    anything contained stays below `_MISS_PENALTY`. A candidate that misses
    scores `_MISS_PENALTY + miss / target`, so every containing candidate
    ranks above every missing one.
    """
    denom = abs(target) if target else None

    def score(lo: float, nom: float, hi: float) -> float:
        if lo <= target <= hi:
            width = hi - lo
            return abs(target - nom) / width if width > 0 else 0.0
        miss = min(abs(target - lo), abs(target - hi))
        return _MISS_PENALTY + miss / (denom if denom is not None else nom)

    return score


def find_best_resistor_config(
    target: float,
    base_table: Sequence[tuple[float, float, float]],
    series_table: Iterable[tuple[float, float, float, int, int]] | None = None,
    parallel_table: Iterable[tuple[float, float, float, int, int]] | None = None,
    n: int = 3,
    configs: Iterable[str] | None = None,
    allow_dominated: bool = False,
) -> list[dict]:
    """Find the best resistor configurations matching a target value.

    Args:
        target: Target resistance in ohms
        base_table: List of (lo, nominal, hi) tuples
        series_table: Series combinations, any iterable of rows (see
            `iter_series_rows`); its indices must refer to `base_table`
        parallel_table: Parallel combinations, any iterable of rows
        n: Number of top results to return
        configs: Which configuration kinds to consider; defaults to all of
            `ALL_CONFIGS`. Filtering happens before ranking, so you always get
            up to `n` results of the kinds you asked for.
        allow_dominated: Keep two-resistor combinations in which one resistor
            alone already covers the target (e.g. "1.58k + 1" for a 1580 target).
            These are strictly worse than that single resistor — two parts, two
            tolerance stacks, no benefit — so they are dropped by default.

    Returns:
        List of dicts with config details, best first.

    Ranking: candidates whose envelope covers the target always come before
    ones that miss it. Among covering candidates, fewer parts wins first (a
    single resistor that covers the target beats a two-resistor combination
    that happens to land dead centre), then the centring score. Among missing
    candidates, the smallest miss wins, then fewer parts.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    enabled = _normalize_configs(configs)

    score_of = _make_scorer(target)

    # A combination is "dominated" when one of its two resistors already covers
    # the target on its own; adding a second part only stacks more tolerance.
    covered = [lo <= target <= hi for lo, _nom, hi in base_table]

    def sort_key(score: float, parts: int) -> tuple[int, float, float]:
        if score < _MISS_PENALTY:
            # Covers the target: prefer fewer parts, then the best centring.
            return (0, parts, score)
        # Misses the target: prefer the smallest miss, then fewer parts.
        return (1, score, parts)

    def candidates():
        if "single" in enabled:
            rank = _CONFIG_RANK["single"]
            for idx, (lo, nom, hi) in enumerate(base_table):
                score = score_of(lo, nom, hi)
                yield (sort_key(score, 1), score, rank, nom, lo, hi, idx, -1)

        for kind, table in (("series", series_table), ("parallel", parallel_table)):
            if kind not in enabled or table is None:
                continue
            rank = _CONFIG_RANK[kind]
            for lo, nom, hi, idx1, idx2 in table:
                i, j = int(idx1), int(idx2)
                if not allow_dominated and (covered[i] or covered[j]):
                    continue
                score = score_of(lo, nom, hi)
                yield (sort_key(score, 2), score, rank, nom, lo, hi, i, j)

    results = []
    for _key, score, rank, nom, lo, hi, idx1, idx2 in heapq.nsmallest(n, candidates()):
        if idx2 < 0:
            resistors = [base_table[idx1][1]]
        else:
            resistors = sorted([base_table[idx1][1], base_table[idx2][1]])
        results.append(_make_result(_RANK_CONFIG[rank], resistors, lo, nom, hi, score))
    return results


def find_bracketing_singles(
    target: float,
    base_table: Sequence[tuple[float, float, float]],
) -> list[dict]:
    """Return the single resistors that bracket the target, in ascending order.

    The nearest value below the target, the exact value if the series has one,
    and the nearest value above it — so two results normally, three when the
    target is itself a standard value. These are the only single resistors worth
    looking at: anything further out is simply further from the target.

    Args:
        target: Target resistance in ohms
        base_table: List of (lo, nominal, hi) tuples

    Returns:
        List of result dicts, each carrying a "position" of "below", "exact"
        or "above", sorted by nominal value
    """
    score_of = _make_scorer(target)
    below = exact = above = None

    for row in base_table:
        nom = row[1]
        if math.isclose(nom, target, rel_tol=1e-12):
            exact = row
        elif nom < target:
            if below is None or nom > below[1]:
                below = row
        else:
            if above is None or nom < above[1]:
                above = row

    results = []
    for position, row in (("below", below), ("exact", exact), ("above", above)):
        if row is None:
            continue
        lo, nom, hi = row
        result = _make_result("single", [nom], lo, nom, hi, score_of(lo, nom, hi))
        result["position"] = position
        results.append(result)
    return results


def _make_result(config: str, resistors: list[float], lo: float, nom: float,
                 hi: float, score: float) -> dict:
    return {
        "config": config,
        "resistors": resistors,
        "nominal": nom,
        "lo": lo,
        "hi": hi,
        "score": score,
        "lower_tol_pct": round((nom - lo) / nom * 100, 4),
        "upper_tol_pct": round((hi - nom) / nom * 100, 4),
    }


def solve(
    target: float,
    es: int = 96,
    precision: int = 3,
    decades: int = 7,
    tolerance: float = 0.01,
    n: int = 5,
    configs: Iterable[str] | None = None,
    values: Iterable[float] | None = None,
    allow_dominated: bool = False,
) -> list[dict]:
    """Convenience wrapper: build the tables for a target and rank them.

    Combination tables are streamed rather than materialized, so wide searches
    (E192 over 10 decades) cost memory proportional to the base table, not to
    its square.

    Args:
        target: Target resistance in ohms
        es: E-series number, used when `values` is None
        precision: Number of significant figures, used when `values` is None
        decades: Number of decades to generate, used when `values` is None
        tolerance: Tolerance as decimal (0.01 = 1%)
        n: Number of top results to return
        configs: Which configuration kinds to consider (see `find_best_resistor_config`)
        values: Explicit resistor values to use instead of an E-series
        allow_dominated: See `find_best_resistor_config`

    Returns:
        List of dicts with config details, sorted by score (best first)
    """
    if not math.isfinite(target) or target <= 0:
        raise ValueError(f"target must be a finite positive resistance, got {target!r}")

    enabled = _normalize_configs(configs)
    base_table = build_base_table(
        es=es, precision=precision, decades=decades, tolerance=tolerance, values=values
    )
    return find_best_resistor_config(
        target,
        base_table,
        iter_series_rows(base_table) if "series" in enabled else None,
        iter_parallel_rows(base_table) if "parallel" in enabled else None,
        n=n,
        configs=enabled,
        allow_dominated=allow_dominated,
    )
