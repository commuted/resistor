"""Core solver for finding optimal resistor configurations."""

import numpy as np

# IEC 60063 standard values for E24 and below.
# These diverge from the mathematical 10^(k/es) formula.
_IEC_E_VALUES = {
    6:  [1.0, 1.5, 2.2, 3.3, 4.7, 6.8],
    12: [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    24: [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
         3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1],
}


def e_decade_table(es: int = 96, precision: int = 3, decade: int = 1) -> np.ndarray:
    """Generate one decade of E-series values with correct significant-figure rounding.

    Args:
        es: E-series number (e.g., 96 for E96)
        precision: Number of significant figures
        decade: Decade number (1 = 1-10Ω, 2 = 10-100Ω, etc.)

    Returns:
        Array of rounded resistor values for one decade
    """
    if es in _IEC_E_VALUES:
        return np.array(_IEC_E_VALUES[es]) * 10 ** (decade - 1)

    k = np.arange(es)
    exponents = k / es
    values = 10.0 ** (exponents + (decade - 1))

    with np.errstate(divide='ignore', invalid='ignore'):
        orders = np.floor(np.log10(np.abs(values)))
        scales = 10.0 ** (precision - 1 - orders.astype(int))
        rounded = np.round(values * scales) / scales

    return rounded


def create_table(es: int = 96, precision: int = 3, decades: int = 6, tolerance: float = 0.01) -> np.ndarray:
    """Create base E-series table with tolerance bounds.

    Args:
        es: E-series number (e.g., 96 for E96)
        precision: Number of significant figures
        decades: Number of decades to generate (1-10Ω, 10-100Ω, etc.)
        tolerance: Tolerance as decimal (0.01 = 1%)

    Returns:
        Array of shape (decades*es, 3) with columns [lo, nominal, hi]
    """
    tables = [
        e_decade_table(es=es, precision=precision, decade=d)
        for d in range(1, decades + 1)
    ]
    nominal = np.concatenate(tables)
    lo = nominal * (1 - tolerance)
    hi = nominal * (1 + tolerance)
    return np.column_stack((lo, nominal, hi))


def create_series_table(base_table: np.ndarray) -> np.ndarray:
    """Create all series combinations from base table.

    Args:
        base_table: Base table of shape (N, 3) with [lo, nominal, hi]

    Returns:
        Array of shape (N*N, 5) with columns [lo, nominal, hi, idx1, idx2]
    """
    n = len(base_table)
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
    lo = base_table[i.ravel(), 0] + base_table[j.ravel(), 0]
    nom = base_table[i.ravel(), 1] + base_table[j.ravel(), 1]
    hi = base_table[i.ravel(), 2] + base_table[j.ravel(), 2]
    return np.column_stack((lo, nom, hi, i.ravel(), j.ravel()))


def create_parallel_table(base_table: np.ndarray) -> np.ndarray:
    """Create all parallel combinations from base table.

    Args:
        base_table: Base table of shape (N, 3) with [lo, nominal, hi]

    Returns:
        Array of shape (N*N, 5) with columns [lo, nominal, hi, idx1, idx2]
    """
    n = len(base_table)
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
    r1 = base_table[i.ravel(), :]
    r2 = base_table[j.ravel(), :]
    nom = (r1[:, 1] * r2[:, 1]) / (r1[:, 1] + r2[:, 1])
    lo = (r1[:, 0] * r2[:, 0]) / (r1[:, 0] + r2[:, 0])
    hi = (r1[:, 2] * r2[:, 2]) / (r1[:, 2] + r2[:, 2])
    return np.column_stack((lo, nom, hi, i.ravel(), j.ravel()))


def find_best_resistor_config(
    target: float,
    base_table: np.ndarray,
    series_table: np.ndarray,
    parallel_table: np.ndarray,
    n: int = 3
) -> list:
    """Find the best resistor configurations matching a target value.

    Args:
        target: Target resistance in ohms
        base_table: Base table of shape (N, 3) with [lo, nominal, hi]
        series_table: Series combinations table of shape (N*N, 5)
        parallel_table: Parallel combinations table of shape (N*N, 5)
        n: Number of top results to return

    Returns:
        List of dicts with config details, sorted by score (best first)
    """
    def get_score(lo, nom, hi):
        inside = (lo <= target) & (target <= hi)
        dist = np.zeros_like(nom, dtype=float)
        outside = ~inside
        if np.any(outside):
            dist[outside] = np.minimum(
                np.abs(target - lo[outside]),
                np.abs(target - hi[outside])
            ) / nom[outside]
        rel_err = np.abs(target - nom) / nom
        return dist + 1e-10 * rel_err

    candidates = []

    # Single resistor
    lo, nom, hi = base_table[:, 0], base_table[:, 1], base_table[:, 2]
    score_single = get_score(lo, nom, hi)
    best_single_idx = np.argsort(score_single)[:n]
    for i in best_single_idx:
        candidates.append({
            "config": "single",
            "resistors": [float(nom[i])],
            "nominal": float(nom[i]),
            "lo": float(lo[i]),
            "hi": float(hi[i]),
            "score": float(score_single[i]),
            "lower_tol_pct": round((nom[i] - lo[i]) / nom[i] * 100, 4),
            "upper_tol_pct": round((hi[i] - nom[i]) / nom[i] * 100, 4)
        })

    # Series combinations
    s_lo, s_nom, s_hi, idx1, idx2 = (series_table[:, i] for i in range(5))
    score_series = get_score(s_lo, s_nom, s_hi)
    best_series_idx = np.argsort(score_series)[:n]
    for i in best_series_idx:
        r1 = float(base_table[int(idx1[i]), 1])
        r2 = float(base_table[int(idx2[i]), 1])
        resistors = sorted([r1, r2])
        candidates.append({
            "config": "series",
            "resistors": resistors,
            "nominal": float(s_nom[i]),
            "lo": float(s_lo[i]),
            "hi": float(s_hi[i]),
            "score": float(score_series[i]),
            "lower_tol_pct": round((s_nom[i] - s_lo[i]) / s_nom[i] * 100, 4),
            "upper_tol_pct": round((s_hi[i] - s_nom[i]) / s_nom[i] * 100, 4)
        })

    # Parallel combinations
    p_lo, p_nom, p_hi, idx1, idx2 = (parallel_table[:, i] for i in range(5))
    score_parallel = get_score(p_lo, p_nom, p_hi)
    best_parallel_idx = np.argsort(score_parallel)[:n]
    for i in best_parallel_idx:
        r1 = float(base_table[int(idx1[i]), 1])
        r2 = float(base_table[int(idx2[i]), 1])
        resistors = sorted([r1, r2])
        candidates.append({
            "config": "parallel",
            "resistors": resistors,
            "nominal": float(p_nom[i]),
            "lo": float(p_lo[i]),
            "hi": float(p_hi[i]),
            "score": float(score_parallel[i]),
            "lower_tol_pct": round((p_nom[i] - p_lo[i]) / p_nom[i] * 100, 4),
            "upper_tol_pct": round((p_hi[i] - p_nom[i]) / p_nom[i] * 100, 4)
        })

    candidates.sort(key=lambda x: x["score"])
    return candidates[:n]
