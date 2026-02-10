"""Core solver for finding optimal resistor configurations."""

import heapq
import math

# IEC 60063 standard values for E24 and below.
# These diverge from the mathematical 10^(k/es) formula.
_IEC_E_VALUES = {
    6:  [1.0, 1.5, 2.2, 3.3, 4.7, 6.8],
    12: [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    24: [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
         3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1],
}


def e_decade_table(es: int = 96, precision: int = 3, decade: int = 1) -> list[float]:
    """Generate one decade of E-series values with correct significant-figure rounding.

    Args:
        es: E-series number (e.g., 96 for E96)
        precision: Number of significant figures
        decade: Decade number (1 = 1-10, 2 = 10-100, etc.)

    Returns:
        List of rounded resistor values for one decade
    """
    if es in _IEC_E_VALUES:
        scale = 10 ** (decade - 1)
        return [v * scale for v in _IEC_E_VALUES[es]]

    scale = 10 ** (decade - 1)
    result = []
    for k in range(es):
        value = 10.0 ** (k / es) * scale
        order = math.floor(math.log10(abs(value)))
        factor = 10.0 ** (precision - 1 - order)
        rounded = round(value * factor) / factor
        result.append(rounded)
    return result


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


def create_series_table(base_table: list[tuple[float, float, float]]) -> list[tuple[float, float, float, int, int]]:
    """Create all series combinations from base table.

    Args:
        base_table: List of (lo, nominal, hi) tuples

    Returns:
        List of (lo, nominal, hi, idx1, idx2) tuples
    """
    n = len(base_table)
    result = []
    for i in range(n):
        lo_i, nom_i, hi_i = base_table[i]
        for j in range(i, n):
            lo_j, nom_j, hi_j = base_table[j]
            result.append((lo_i + lo_j, nom_i + nom_j, hi_i + hi_j, i, j))
    return result


def create_parallel_table(base_table: list[tuple[float, float, float]]) -> list[tuple[float, float, float, int, int]]:
    """Create all parallel combinations from base table.

    Args:
        base_table: List of (lo, nominal, hi) tuples

    Returns:
        List of (lo, nominal, hi, idx1, idx2) tuples
    """
    n = len(base_table)
    result = []
    for i in range(n):
        lo_i, nom_i, hi_i = base_table[i]
        for j in range(i, n):
            lo_j, nom_j, hi_j = base_table[j]
            nom = (nom_i * nom_j) / (nom_i + nom_j)
            lo = (lo_i * lo_j) / (lo_i + lo_j)
            hi = (hi_i * hi_j) / (hi_i + hi_j)
            result.append((lo, nom, hi, i, j))
    return result


def find_best_resistor_config(
    target: float,
    base_table: list[tuple[float, float, float]],
    series_table: list[tuple[float, float, float, int, int]],
    parallel_table: list[tuple[float, float, float, int, int]],
    n: int = 3
) -> list:
    """Find the best resistor configurations matching a target value.

    Args:
        target: Target resistance in ohms
        base_table: List of (lo, nominal, hi) tuples
        series_table: Series combinations list
        parallel_table: Parallel combinations list
        n: Number of top results to return

    Returns:
        List of dicts with config details, sorted by score (best first)
    """
    def get_score(lo, nom, hi):
        if lo <= target <= hi:
            dist = 0.0
        else:
            dist = min(abs(target - lo), abs(target - hi)) / nom
        rel_err = abs(target - nom) / nom
        return dist + 1e-10 * rel_err

    def make_result(config, resistors, lo, nom, hi, score):
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

    candidates = []

    # Single resistors
    scored_singles = []
    for row in base_table:
        lo, nom, hi = row
        score = get_score(lo, nom, hi)
        scored_singles.append((score, lo, nom, hi))
    for score, lo, nom, hi in heapq.nsmallest(n, scored_singles):
        candidates.append(make_result("single", [nom], lo, nom, hi, score))

    # Series combinations
    scored_series = []
    for row in series_table:
        lo, nom, hi, idx1, idx2 = row
        score = get_score(lo, nom, hi)
        scored_series.append((score, lo, nom, hi, idx1, idx2))
    for score, lo, nom, hi, idx1, idx2 in heapq.nsmallest(n, scored_series):
        r1 = base_table[int(idx1)][1]
        r2 = base_table[int(idx2)][1]
        resistors = sorted([r1, r2])
        candidates.append(make_result("series", resistors, lo, nom, hi, score))

    # Parallel combinations
    scored_parallel = []
    for row in parallel_table:
        lo, nom, hi, idx1, idx2 = row
        score = get_score(lo, nom, hi)
        scored_parallel.append((score, lo, nom, hi, idx1, idx2))
    for score, lo, nom, hi, idx1, idx2 in heapq.nsmallest(n, scored_parallel):
        r1 = base_table[int(idx1)][1]
        r2 = base_table[int(idx2)][1]
        resistors = sorted([r1, r2])
        candidates.append(make_result("parallel", resistors, lo, nom, hi, score))

    candidates.sort(key=lambda x: x["score"])
    return candidates[:n]
