"""Regression tests for the bugs fixed in 0.3.0."""

import math
import pathlib

import pytest

from resistor.cli import build_parser, main, parse_resistance, parse_stock
from resistor.solver import (
    build_base_table,
    create_table,
    e_decade_table,
    find_best_resistor_config,
    find_bracketing_singles,
    iter_parallel_rows,
    iter_series_rows,
    solve,
)


def covers(value, target):
    return value * 0.99 <= target <= value * 1.01


class TestDominatedCombinations:
    """A pair is pointless when one of its resistors already covers the target."""

    def test_no_dominated_pairs_in_deep_result(self):
        results = solve(1580, decades=6, n=60)
        assert len(results) == 60
        for r in results:
            if len(r["resistors"]) == 2:
                assert not any(covers(v, 1580) for v in r["resistors"]), r["resistors"]

    def test_target_plus_trim_resistor_is_hidden(self):
        """"1.58k + 1" must not appear for a 1580 target."""
        pairs = [tuple(r["resistors"]) for r in solve(1580, decades=6, n=60)]
        assert (1.0, 1580.0) not in pairs

    def test_allow_dominated_brings_them_back(self):
        results = solve(1580, decades=6, n=60, allow_dominated=True)
        dominated = [r for r in results
                     if len(r["resistors"]) == 2
                     and any(covers(v, 1580) for v in r["resistors"])]
        assert dominated

    def test_genuine_trim_pairs_survive(self):
        """40.2 + 1.54k is legitimate: neither part covers 1580 alone."""
        pairs = [tuple(r["resistors"]) for r in solve(1580, decades=6, n=60)]
        assert (40.2, 1540.0) in pairs

    def test_exact_single_still_ranks_first(self):
        results = solve(1580, decades=6, n=5)
        assert results[0]["config"] == "single"
        assert results[0]["nominal"] == 1580.0


class TestRanking:
    """Covering candidates beat misses; fewer parts beats dead-centre pairs."""

    def test_covering_single_beats_exact_pair(self):
        """2.21k covers 2200 within 1%, so it outranks exact two-part sums."""
        results = solve(2200, decades=6, n=5)
        assert results[0]["config"] == "single"
        assert results[0]["nominal"] == 2210.0

    def test_covering_beats_missing(self):
        results = solve(1234, decades=6, n=30)
        covering = [i for i, r in enumerate(results) if r["lo"] <= 1234 <= r["hi"]]
        missing = [i for i, r in enumerate(results) if not r["lo"] <= 1234 <= r["hi"]]
        assert not missing or not covering or max(covering) < min(missing)

    def test_centred_match_scores_zero(self):
        results = solve(1580, decades=6, n=1)
        assert results[0]["score"] == 0.0

    def test_miss_scores_above_one(self):
        results = solve(0.1, decades=6, n=1, configs=["single"])
        assert results[0]["score"] > 1.0

    def test_zero_tolerance_does_not_divide_by_zero(self):
        results = solve(1580, decades=6, tolerance=0.0, n=3)
        assert results[0]["nominal"] == 1580.0
        assert results[0]["score"] == 0.0


class TestConfigFiltering:
    """Filtering happens before ranking, so you always get n results."""

    def test_single_only_returns_results(self):
        results = solve(1234, decades=6, n=5, configs=["single"])
        assert len(results) == 5
        assert all(r["config"] == "single" for r in results)
        assert results[0]["nominal"] == 1240.0

    def test_series_only_returns_requested_count(self):
        results = solve(1234, decades=6, n=5, configs=["series"])
        assert len(results) == 5
        assert all(r["config"] == "series" for r in results)

    def test_parallel_only_returns_requested_count(self):
        results = solve(1234, decades=6, n=5, configs=["parallel"])
        assert len(results) == 5
        assert all(r["config"] == "parallel" for r in results)

    def test_unknown_config_rejected(self):
        with pytest.raises(ValueError):
            solve(1000, n=1, configs=["bridge"])

    def test_empty_config_rejected(self):
        with pytest.raises(ValueError):
            solve(1000, n=1, configs=[])

    def test_cli_flags_are_mutually_exclusive(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["1580", "--single-only", "--series-only"])

    def test_cli_single_only_prints_a_match(self, capsys):
        main(["1234", "--single-only", "-n", "3"])
        out = capsys.readouterr().out
        assert "No matching configurations found." not in out
        assert "SINGLE 1.24k" in out


class TestGroupedOutput:
    """One ranking per part count, so the groups never compete."""

    def test_both_groups_present(self, capsys):
        main(["2200", "-n", "3"])
        out = capsys.readouterr().out
        assert "One resistor" in out
        assert "Two resistors" in out
        assert out.index("One resistor") < out.index("Two resistors")

    def test_num_results_applies_to_the_two_part_group(self, capsys):
        main(["2200", "-n", "4"])
        one, two = capsys.readouterr().out.split("Two resistors")
        assert two.count("Nominal:") == 4
        assert one.count("Nominal:") == 2  # bracketing values only

    def test_two_part_group_ranks_centre_out(self, capsys):
        main(["2200", "-n", "6"])
        two = capsys.readouterr().out.split("Two resistors")[1]
        errors = [abs(float(line.split("(")[1].split("%")[0]))
                  for line in two.splitlines() if "Nominal:" in line]
        assert errors == sorted(errors)

    def test_single_only_omits_two_part_group(self, capsys):
        main(["1580", "--single-only", "-n", "2"])
        out = capsys.readouterr().out
        assert "One resistor" in out
        assert "Two resistors" not in out

    def test_series_only_labels_the_group(self, capsys):
        main(["1580", "--series-only", "-n", "2"])
        out = capsys.readouterr().out
        assert "Two resistors (series only)" in out
        assert "One resistor" not in out
        assert "PARALLEL" not in out

    def test_parallel_only_labels_the_group(self, capsys):
        main(["1580", "--parallel-only", "-n", "2"])
        out = capsys.readouterr().out
        assert "Two resistors (parallel only)" in out
        assert "SERIES" not in out

    def test_exact_single_is_labelled_in_its_own_group(self, capsys):
        main(["1580", "-n", "3"])
        one = capsys.readouterr().out.split("Two resistors")[0]
        assert "exact: SINGLE 1.58k" in one

    def test_offcentre_single_still_gets_its_own_group(self, capsys):
        """2.21k covers 2200 but is off centre; it leads the one-part group anyway."""
        main(["2200", "-n", "3"])
        out = capsys.readouterr().out
        one_part = out.split("Two resistors")[0]
        assert "SINGLE 2.21k" in one_part
        assert "+0.4545%" in one_part


class TestInputValidation:
    @pytest.mark.parametrize("argv", [
        ["0"], ["-100"], ["inf"], ["nan"], ["abc"],
        ["1580", "-n", "0"], ["1580", "-n", "-2"],
        ["1580", "-d", "0"], ["1580", "-d", "11"],
        ["1580", "-t", "-1"], ["1580", "-t", "100"],
    ])
    def test_bad_input_exits_with_usage_error(self, argv):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2

    def test_solver_rejects_non_positive_target(self):
        with pytest.raises(ValueError):
            solve(0, n=1)
        with pytest.raises(ValueError):
            solve(float("inf"), n=1)

    def test_solver_rejects_zero_results(self):
        base = create_table(es=24, decades=1)
        with pytest.raises(ValueError):
            find_best_resistor_config(100, base, n=0)


class TestResistanceParsing:
    @pytest.mark.parametrize("text,expected", [
        ("1000", 1000.0), ("4.7k", 4700.0), ("4k7", 4700.0), ("4K7", 4700.0),
        ("2.2M", 2.2e6), ("2M2", 2.2e6), ("470R", 470.0), ("4R7", 4.7),
        ("1R", 1.0), ("1e3", 1000.0), ("  1k  ", 1000.0),
    ])
    def test_accepted(self, text, expected):
        assert parse_resistance(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", ["inf", "-inf", "nan", "1.5k5", "abc", "", "  ", None])
    def test_rejected(self, text):
        assert parse_resistance(text) is None


class TestStockList:
    def test_inline_list(self):
        assert parse_stock("1k,470,120,2k2") == [120.0, 470.0, 1000.0, 2200.0]

    def test_file_with_comments(self, tmp_path):
        path = tmp_path / "parts.txt"
        path.write_text("# junk box\n1k  470\n120\n2k2  # dupes below\n1k\n")
        assert parse_stock(f"@{path}") == [120.0, 470.0, 1000.0, 2200.0]

    def test_bad_value_exits(self):
        with pytest.raises(SystemExit) as exc:
            parse_stock("1k,wat")
        assert exc.value.code == 1

    def test_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            parse_stock(f"@{tmp_path / 'nope.txt'}")
        assert exc.value.code == 1

    def test_solve_with_stock_only_uses_stock_values(self):
        stock = [120.0, 470.0, 1000.0, 2200.0]
        results = solve(1470, values=stock, n=5)
        assert results[0]["resistors"] == [470.0, 1000.0]
        for r in results:
            assert all(v in stock for v in r["resistors"])

    def test_build_base_table_rejects_bad_values(self):
        with pytest.raises(ValueError):
            build_base_table(values=[1000.0, -5.0])
        with pytest.raises(ValueError):
            build_base_table(values=[])


class TestDecadeCoverage:
    def test_default_decades_reach_22m(self):
        """resistor 2.2M (a documented example) must find a covering config."""
        results = solve(2.2e6, n=1)
        assert results[0]["lo"] <= 2.2e6 <= results[0]["hi"]

    def test_warning_when_target_unreachable(self, capsys):
        main(["50M", "-n", "1"])
        captured = capsys.readouterr()
        assert "does NOT cover target" in captured.out
        assert "no configuration's tolerance envelope covers the target" in captured.err
        assert "outside the reachable range" in captured.err

    def test_no_warning_for_a_good_match(self, capsys):
        """1580 is covered, so no warning — even though the bracketing
        neighbours in the one-part group are not."""
        main(["1580", "-n", "3"])
        captured = capsys.readouterr()
        assert captured.err == ""
        assert "exact: SINGLE 1.58k" in captured.out
        two_part = captured.out.split("Two resistors")[1]
        assert "does NOT cover target" not in two_part


class TestDecadeScalingExactness:
    """E6/E12/E24 values must stay exact after decade scaling."""

    @pytest.mark.parametrize("es", [6, 12, 24])
    @pytest.mark.parametrize("decade", range(1, 11))
    def test_values_are_clean(self, es, decade):
        base = e_decade_table(es=es, decade=1)
        scaled = e_decade_table(es=es, decade=decade)
        scale = 10 ** (decade - 1)
        for b, v in zip(base, scaled):
            assert v == pytest.approx(b * scale, rel=1e-12)
            # Exactly representable at 3 significant figures, no float fuzz.
            assert v == float(f"{v:.3g}")

    def test_known_scaled_values_exact(self):
        d3 = e_decade_table(es=24, decade=3)
        assert 110.0 in d3
        assert 220.0 in d3
        assert 510.0 in d3
        assert 820.0 in d3


class TestStreamingTables:
    def test_iterators_match_materialized_tables(self):
        base = create_table(es=24, decades=1)
        assert list(iter_series_rows(base)) == list(iter_series_rows(base))
        assert len(list(iter_series_rows(base))) == 24 * 25 // 2
        assert len(list(iter_parallel_rows(base))) == 24 * 25 // 2

    def test_find_best_accepts_generators(self):
        base = create_table(es=96, decades=4)
        results = find_best_resistor_config(
            1580, base, iter_series_rows(base), iter_parallel_rows(base), n=5
        )
        assert len(results) == 5
        assert results[0]["nominal"] == 1580.0

    def test_single_only_needs_no_combination_tables(self):
        base = create_table(es=96, decades=6)
        results = find_best_resistor_config(1580, base, None, None, n=3, configs=["single"])
        assert [r["config"] for r in results] == ["single"] * 3

    def test_wide_search_is_not_quadratic_in_memory(self):
        import tracemalloc
        base = build_base_table(es=192, decades=5)
        tracemalloc.start()
        find_best_resistor_config(
            1580, base, iter_series_rows(base), iter_parallel_rows(base), n=5
        )
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        # The N^2 tables would be hundreds of MB; streaming stays tiny.
        assert peak < 5 * 1024 * 1024, peak


class TestToleranceReporting:
    def test_tolerance_percentages_are_reported(self, capsys):
        main(["1580", "-n", "1", "-t", "5"])
        out = capsys.readouterr().out
        assert "(-5%/+5%)" in out

    def test_envelope_matches_tolerance(self):
        results = solve(1580, decades=6, tolerance=0.05, n=4)
        for r in results:
            assert r["lower_tol_pct"] == pytest.approx(5.0, abs=1e-6)
            assert r["upper_tol_pct"] == pytest.approx(5.0, abs=1e-6)
            assert math.isclose(r["lo"], r["nominal"] * 0.95, rel_tol=1e-9)


class TestBracketingSingles:
    """The one-resistor group brackets the target: below, exact, above."""

    @pytest.fixture
    def base(self):
        return build_base_table(es=96, decades=6)

    def test_exact_target_gives_three(self, base):
        results = find_bracketing_singles(1580, base)
        assert [r["position"] for r in results] == ["below", "exact", "above"]
        assert [r["nominal"] for r in results] == [1540.0, 1580.0, 1620.0]

    def test_target_between_values_gives_two(self, base):
        results = find_bracketing_singles(2200, base)
        assert [r["position"] for r in results] == ["below", "above"]
        assert [r["nominal"] for r in results] == [2150.0, 2210.0]

    def test_ascending_and_bracketing(self, base):
        for target in (1234, 47.5, 68000, 2.2e6):
            results = find_bracketing_singles(target, base)
            noms = [r["nominal"] for r in results]
            assert noms == sorted(noms)
            below = [r["nominal"] for r in results if r["position"] == "below"]
            above = [r["nominal"] for r in results if r["position"] == "above"]
            assert all(v < target for v in below)
            assert all(v > target for v in above)

    def test_below_range_has_no_below(self, base):
        results = find_bracketing_singles(0.5, base)
        assert [r["position"] for r in results] == ["above"]
        assert results[0]["nominal"] == 1.0

    def test_above_range_has_no_above(self, base):
        results = find_bracketing_singles(5e7, base)
        assert [r["position"] for r in results] == ["below"]
        assert results[0]["nominal"] == 976000.0

    def test_exact_match_scores_zero(self, base):
        exact = [r for r in find_bracketing_singles(1580, base) if r["position"] == "exact"]
        assert exact[0]["score"] == 0.0

    def test_result_shape_matches_solver(self, base):
        result = find_bracketing_singles(1580, base)[0]
        assert set(result) == {"config", "resistors", "nominal", "lo", "hi",
                               "score", "lower_tol_pct", "upper_tol_pct", "position"}
        assert result["config"] == "single"
        assert len(result["resistors"]) == 1

    def test_works_with_a_stock_table(self):
        base = build_base_table(values=[120, 470, 1000, 2200])
        results = find_bracketing_singles(1580, base)
        assert [r["nominal"] for r in results] == [1000.0, 2200.0]

    def test_cli_prints_three_rows_on_exact_match(self, capsys):
        main(["1580", "--single-only"])
        out = capsys.readouterr().out
        assert out.count("Nominal:") == 3
        for tag in ("below:", "exact:", "above:"):
            assert tag in out
        assert out.index("below:") < out.index("exact:") < out.index("above:")

    def test_cli_prints_two_rows_otherwise(self, capsys):
        main(["2200", "--single-only"])
        out = capsys.readouterr().out
        assert out.count("Nominal:") == 2
        assert "exact:" not in out

    def test_cli_ignores_n_for_the_single_group(self, capsys):
        main(["1580", "--single-only", "-n", "9"])
        assert capsys.readouterr().out.count("Nominal:") == 3


class TestHelpScreen:
    def test_help_points_at_the_issue_tracker(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Report bugs at: https://github.com/commuted/resistor/issues" in out

    def test_issues_url_matches_the_repo(self):
        from resistor.cli import ISSUES_URL
        pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        repo = None
        for line in pyproject.read_text().splitlines():
            if line.startswith("Repository ="):
                repo = line.split("=", 1)[1].strip().strip('"')
        assert repo is not None
        assert ISSUES_URL == f"{repo}/issues"
