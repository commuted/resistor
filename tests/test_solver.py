"""Unit tests for resistor solver."""

import numpy as np
import pytest

from resistor.solver import (
    e_decade_table,
    create_table,
    create_series_table,
    create_parallel_table,
    find_best_resistor_config,
)


class TestEDecadeTable:
    """Tests for e_decade_table function."""

    def test_e96_first_decade_length(self):
        """E96 should produce 96 values per decade."""
        result = e_decade_table(es=96, decade=1)
        assert len(result) == 96

    def test_e24_first_decade_length(self):
        """E24 should produce 24 values per decade."""
        result = e_decade_table(es=24, decade=1)
        assert len(result) == 24

    def test_first_value_is_one(self):
        """First value of decade 1 should be 1.0."""
        result = e_decade_table(es=96, decade=1)
        assert result[0] == 1.0

    def test_decade_scaling(self):
        """Decade 2 values should be 10x decade 1."""
        d1 = e_decade_table(es=96, decade=1)
        d2 = e_decade_table(es=96, decade=2)
        np.testing.assert_allclose(d2, d1 * 10, rtol=1e-6)

    def test_values_are_increasing(self):
        """Values within a decade should be monotonically increasing."""
        result = e_decade_table(es=96, decade=1)
        assert np.all(np.diff(result) > 0)

    def test_known_e96_values(self):
        """Check some known E96 standard values exist."""
        result = e_decade_table(es=96, decade=1)
        # Some standard E96 values in first decade
        expected_values = [1.0, 1.1, 1.21, 1.33, 1.47, 1.62, 1.78, 1.96]
        for val in expected_values:
            assert np.any(np.isclose(result, val, rtol=0.01)), f"{val} not found"


    def test_e24_iec_standard_values(self):
        """E24 first-decade values should match IEC 60063 exactly."""
        result = e_decade_table(es=24, decade=1)
        expected = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
                    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
        np.testing.assert_array_equal(result, expected)

    def test_e12_iec_standard_values(self):
        """E12 first-decade values should match IEC 60063 exactly."""
        result = e_decade_table(es=12, decade=1)
        expected = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
        np.testing.assert_array_equal(result, expected)

    def test_e6_iec_standard_values(self):
        """E6 first-decade values should match IEC 60063 exactly."""
        result = e_decade_table(es=6, decade=1)
        expected = [1.0, 1.5, 2.2, 3.3, 4.7, 6.8]
        np.testing.assert_array_equal(result, expected)

    def test_e12_subset_of_e24(self):
        """E12 values should be a subset of E24."""
        e12 = set(e_decade_table(es=12, decade=1))
        e24 = set(e_decade_table(es=24, decade=1))
        assert e12.issubset(e24)

    def test_e6_subset_of_e12(self):
        """E6 values should be a subset of E12."""
        e6 = set(e_decade_table(es=6, decade=1))
        e12 = set(e_decade_table(es=12, decade=1))
        assert e6.issubset(e12)

    def test_e24_decade_scaling(self):
        """E24 decade 2 values should be 10x decade 1."""
        d1 = e_decade_table(es=24, decade=1)
        d2 = e_decade_table(es=24, decade=2)
        np.testing.assert_allclose(d2, d1 * 10, rtol=1e-10)


class TestCreateTable:
    """Tests for create_table function."""

    def test_output_shape(self):
        """Output should have shape (decades*es, 3)."""
        result = create_table(es=96, decades=6)
        assert result.shape == (576, 3)

    def test_columns_are_lo_nom_hi(self):
        """Columns should be [lo, nominal, hi] with lo < nom < hi."""
        result = create_table(es=96, decades=1)
        lo, nom, hi = result[:, 0], result[:, 1], result[:, 2]
        assert np.all(lo < nom)
        assert np.all(nom < hi)

    def test_tolerance_bounds(self):
        """Tolerance bounds should match specified tolerance."""
        result = create_table(es=96, decades=1, tolerance=0.01)
        lo, nom, hi = result[:, 0], result[:, 1], result[:, 2]
        np.testing.assert_allclose(lo, nom * 0.99, rtol=1e-10)
        np.testing.assert_allclose(hi, nom * 1.01, rtol=1e-10)

    def test_custom_tolerance(self):
        """Custom tolerance should be applied correctly."""
        result = create_table(es=96, decades=1, tolerance=0.05)
        lo, nom, hi = result[:, 0], result[:, 1], result[:, 2]
        np.testing.assert_allclose(lo, nom * 0.95, rtol=1e-10)
        np.testing.assert_allclose(hi, nom * 1.05, rtol=1e-10)

    def test_range_coverage(self):
        """6 decades should cover 1 ohm to ~1M ohm."""
        result = create_table(es=96, decades=6)
        nom = result[:, 1]
        assert nom.min() == 1.0
        assert nom.max() > 900000  # Close to 1M


class TestCreateSeriesTable:
    """Tests for create_series_table function."""

    def test_output_shape(self):
        """Output should have shape (N*N, 5)."""
        base = create_table(es=24, decades=1)  # Small for speed
        result = create_series_table(base)
        assert result.shape == (24 * 24, 5)

    def test_series_sum_correct(self):
        """Series nominal should equal R1 + R2."""
        base = create_table(es=24, decades=1)
        result = create_series_table(base)
        # Check a few random entries
        for i in [0, 100, 500]:
            idx1, idx2 = int(result[i, 3]), int(result[i, 4])
            expected = base[idx1, 1] + base[idx2, 1]
            assert result[i, 1] == expected

    def test_indices_valid(self):
        """Stored indices should be valid."""
        base = create_table(es=24, decades=1)
        result = create_series_table(base)
        indices = result[:, 3:5].astype(int)
        assert np.all(indices >= 0)
        assert np.all(indices < len(base))


class TestCreateParallelTable:
    """Tests for create_parallel_table function."""

    def test_output_shape(self):
        """Output should have shape (N*N, 5)."""
        base = create_table(es=24, decades=1)
        result = create_parallel_table(base)
        assert result.shape == (24 * 24, 5)

    def test_parallel_formula_correct(self):
        """Parallel nominal should equal (R1*R2)/(R1+R2)."""
        base = create_table(es=24, decades=1)
        result = create_parallel_table(base)
        for i in [0, 100, 500]:
            idx1, idx2 = int(result[i, 3]), int(result[i, 4])
            r1, r2 = base[idx1, 1], base[idx2, 1]
            expected = (r1 * r2) / (r1 + r2)
            np.testing.assert_allclose(result[i, 1], expected, rtol=1e-10)

    def test_parallel_less_than_either(self):
        """Parallel combination should be less than either resistor."""
        base = create_table(es=24, decades=1)
        result = create_parallel_table(base)
        for i in [0, 100, 500]:
            idx1, idx2 = int(result[i, 3]), int(result[i, 4])
            r1, r2 = base[idx1, 1], base[idx2, 1]
            assert result[i, 1] < r1 or np.isclose(r1, r2)
            assert result[i, 1] < r2 or np.isclose(r1, r2)


class TestFindBestResistorConfig:
    """Tests for find_best_resistor_config function."""

    @pytest.fixture
    def tables(self):
        """Create standard tables for testing."""
        base = create_table(es=96, decades=6)
        series = create_series_table(base)
        parallel = create_parallel_table(base)
        return base, series, parallel

    def test_returns_list(self, tables):
        """Should return a list."""
        base, series, parallel = tables
        result = find_best_resistor_config(1000, base, series, parallel)
        assert isinstance(result, list)

    def test_returns_n_results(self, tables):
        """Should return requested number of results."""
        base, series, parallel = tables
        result = find_best_resistor_config(1000, base, series, parallel, n=5)
        assert len(result) == 5

    def test_results_sorted_by_score(self, tables):
        """Results should be sorted by score ascending."""
        base, series, parallel = tables
        result = find_best_resistor_config(1234, base, series, parallel, n=10)
        scores = [r["score"] for r in result]
        assert scores == sorted(scores)

    def test_exact_match_has_zero_score(self, tables):
        """An exact E96 value should have score near zero."""
        base, series, parallel = tables
        # 1000 ohms is an E96 value
        result = find_best_resistor_config(1000, base, series, parallel, n=1)
        assert result[0]["score"] < 1e-8

    def test_result_structure(self, tables):
        """Results should have expected keys."""
        base, series, parallel = tables
        result = find_best_resistor_config(1000, base, series, parallel, n=1)
        expected_keys = {"config", "resistors", "nominal", "lo", "hi", "score",
                        "lower_tol_pct", "upper_tol_pct"}
        assert set(result[0].keys()) == expected_keys

    def test_config_types(self, tables):
        """Config should be one of single/series/parallel."""
        base, series, parallel = tables
        result = find_best_resistor_config(1580, base, series, parallel, n=10)
        for r in result:
            assert r["config"] in {"single", "series", "parallel"}

    def test_single_has_one_resistor(self, tables):
        """Single config should have one resistor."""
        base, series, parallel = tables
        result = find_best_resistor_config(1000, base, series, parallel, n=10)
        singles = [r for r in result if r["config"] == "single"]
        for s in singles:
            assert len(s["resistors"]) == 1

    def test_series_parallel_have_two_resistors(self, tables):
        """Series and parallel configs should have two resistors."""
        base, series, parallel = tables
        result = find_best_resistor_config(1580, base, series, parallel, n=10)
        combos = [r for r in result if r["config"] in {"series", "parallel"}]
        for c in combos:
            assert len(c["resistors"]) == 2

    def test_tolerance_percentage_correct(self, tables):
        """Tolerance percentages should match 1% tolerance."""
        base, series, parallel = tables
        result = find_best_resistor_config(1000, base, series, parallel, n=1)
        # For 1% tolerance, should be close to 1.0
        assert 0.99 < result[0]["lower_tol_pct"] < 1.01
        assert 0.99 < result[0]["upper_tol_pct"] < 1.01

    def test_target_outside_range(self, tables):
        """Should still return results for targets outside normal range."""
        base, series, parallel = tables
        # Very small target
        result = find_best_resistor_config(0.1, base, series, parallel, n=1)
        assert len(result) == 1
        assert result[0]["score"] > 0  # Won't be exact match

    def test_specific_value_1580(self, tables):
        """Verify known result for 1580 ohms."""
        base, series, parallel = tables
        result = find_best_resistor_config(1580, base, series, parallel, n=1)
        # 1580 is an E96 value, should find exact match
        assert result[0]["config"] == "single"
        assert result[0]["nominal"] == 1580.0
        assert result[0]["score"] < 1e-8


class TestCLIParsing:
    """Tests for CLI helper functions."""

    def test_parse_resistance_plain(self):
        from resistor.cli import parse_resistance
        assert parse_resistance("1000") == 1000.0

    def test_parse_resistance_kilo(self):
        from resistor.cli import parse_resistance
        assert parse_resistance("4.7k") == 4700.0
        assert parse_resistance("4.7K") == 4700.0

    def test_parse_resistance_mega(self):
        from resistor.cli import parse_resistance
        assert parse_resistance("2.2M") == 2200000.0
        assert parse_resistance("2.2m") == 2200000.0

    def test_parse_resistance_invalid(self):
        from resistor.cli import parse_resistance
        assert parse_resistance("abc") is None

    def test_format_resistance_ohms(self):
        from resistor.cli import format_resistance
        assert format_resistance(100) == "100"

    def test_format_resistance_kilo(self):
        from resistor.cli import format_resistance
        assert format_resistance(4700) == "4.7k"

    def test_format_resistance_mega(self):
        from resistor.cli import format_resistance
        assert format_resistance(2200000) == "2.2M"
