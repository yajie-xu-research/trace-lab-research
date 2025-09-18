"""Perturbation injection and held-out evaluation tests."""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from trace_lab.p2.constants import CATEGORIES


def _plan(synthetic) -> list[dict]:
    return json.loads((synthetic / "perturbation_library.json").read_text())["perturbations"]


def test_perturbation_library_schema(synthetic):
    plan = json.loads((synthetic / "perturbation_library.json").read_text())
    assert plan["seed"] == 20250110
    required = {"perturbation_id", "kind", "node_id", "true_category",
                "window_start", "window_end", "change_id", "lineage_break"}
    for p in plan["perturbations"]:
        assert required <= set(p)


def test_shift_injection_moves_values(synthetic, observation):
    for p in _plan(synthetic):
        if p["true_category"] == "FIELD_SEMANTIC_CHANGE" and float(p["shift_magnitude"]) > 0:
            seg = observation[
                (observation.node_id == p["node_id"])
                & (observation.observed_at_utc >= p["window_start"])
                & (observation.observed_at_utc < p["window_end"])]
            assert len(seg) >= 2
            assert seg["parsed_value"].astype(float).mean() > 3.0


def test_unit_change_injection(synthetic, observation):
    for p in _plan(synthetic):
        if p["true_category"] == "UNIT_CHANGE":
            assert p["wrong_unit"]
            seg = observation[
                (observation.node_id == p["node_id"])
                & (observation.observed_at_utc >= p["window_start"])
                & (observation.observed_at_utc < p["window_end"])]
            assert len(seg) >= 1
            assert seg["reported_unit"].str.contains(p["wrong_unit"]).any()


def test_missing_injection_empties_values(synthetic, observation):
    # Extraction failures are written as rows with empty values (not dropped
    # rows), so the missing-rate detector sees a burst of missing content.
    for p in _plan(synthetic):
        if p["true_category"] == "EXTRACTION_FAILURE":
            assert float(p["missing_fraction"]) > 0
            seg = observation[
                (observation.node_id == p["node_id"])
                & (observation.observed_at_utc >= p["window_start"])
                & (observation.observed_at_utc < p["window_end"])]
            assert len(seg) >= 2
            missing = (seg["raw_value"] == "").sum()
            assert missing >= max(1, int(len(seg) * float(p["missing_fraction"]) * 0.5))


def test_garble_tokens_fail_format_pattern(synthetic, observation):
    allowed = re.compile(r"^[A-Za-z0-9_. \-]{1,64}$")
    seen_bad = []
    for p in _plan(synthetic):
        if float(p["garble_fraction"]) > 0:
            seg = observation[
                (observation.node_id == p["node_id"])
                & (observation.observed_at_utc >= p["window_start"])
                & (observation.observed_at_utc < p["window_end"])]
            # The injected garble tokens must genuinely fail the pattern;
            # ordinary rows in the same window (e.g. out-of-range numerics
            # from a neighbouring interface event) are allowed to pass.
            bad = [t for t in seg["raw_value"].tolist()
                   if not allowed.match(str(t))]
            assert bad, p["perturbation_id"]
            seen_bad.extend(bad)
    assert seen_bad


def test_evaluation_reports_six_categories(evaluation_run):
    report = json.loads((evaluation_run / "evaluation_report.json").read_text())
    main = report["TRACE_LAB_MAIN"]
    assert set(main["per_category_precision"]) == set(CATEGORIES)
    assert set(main["per_category_recall"]) == set(CATEGORIES)


def test_evaluation_metrics_in_expected_ranges(evaluation_run):
    report = json.loads((evaluation_run / "evaluation_report.json").read_text())
    main = report["TRACE_LAB_MAIN"]
    assert 0.0 <= main["false_positive_rate_on_controls"] <= 0.05
    for cat, p in main["per_category_precision"].items():
        if p is not None:
            assert 0.8 <= p <= 1.0, cat
    for cat, r in main["per_category_recall"].items():
        if r is not None:
            assert 0.6 <= r <= 1.0, cat
    assert main["unknown_mis_triaged"] == 0


def test_baselines_do_not_beat_main_method(evaluation_run):
    report = json.loads((evaluation_run / "evaluation_report.json").read_text())
    main = report["TRACE_LAB_MAIN"]
    for b in ("B0_SINGLE_FIELD_RULES", "B1_NO_LINEAGE_DETECTION",
              "B2_CHANGE_POINT_ONLY", "B3_SITE_MAPPING_TABLE"):
        assert b in report, b
        assert report[b]["false_positive_rate_on_controls"] >= main["false_positive_rate_on_controls"], b


def test_evaluation_summary_written(evaluation_run):
    summary = (evaluation_run / "evaluation_summary.md").read_text()
    assert "Per-category precision / recall" in summary
    assert "abstain" in summary


def test_baselines_report_rows(evaluation_run):
    df = pd.read_csv(evaluation_run / "baselines_report.csv", keep_default_na=False)
    assert set(df["method"]) >= {"TRACE_LAB_MAIN", "B0_SINGLE_FIELD_RULES",
                                 "B1_NO_LINEAGE_DETECTION", "B2_CHANGE_POINT_ONLY",
                                 "B3_SITE_MAPPING_TABLE"}
