"""Triage behavior tests covering the counter-example table:
lineage breakage abstention, ambiguous near-coincident changes, negative
controls, and decision/reason codes."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from trace_lab.p2.constants import (
    DECISION_ABSTAIN,
    DECISION_TRIAGE,
    REASON_AMBIGUOUS_CANDIDATES,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_LINEAGE_UNRESOLVED,
)


def _split_ids(value: str) -> list[str]:
    return [part for part in str(value).replace("|", ",").split(",") if part.strip()]


def test_decisions_are_two_valued(triage_results):
    assert set(triage_results["decision"]) <= {DECISION_TRIAGE, DECISION_ABSTAIN}


def test_reason_codes_restricted(triage_results):
    codes = set(triage_results.loc[triage_results.decision == DECISION_ABSTAIN, "reason_code"])
    assert codes <= {REASON_AMBIGUOUS_CANDIDATES, REASON_LINEAGE_UNRESOLVED,
                     REASON_INSUFFICIENT_EVIDENCE}


def test_lineage_broken_chain_abstains(triage_results):
    broken = triage_results[
        (triage_results.node_id == "N028") & (triage_results.decision == DECISION_ABSTAIN)]
    assert len(broken) >= 1
    assert (broken["reason_code"] == REASON_LINEAGE_UNRESOLVED).any()


def test_ambiguous_nearby_changes_abstain(triage_results):
    amb = triage_results[triage_results.reason_code == REASON_AMBIGUOUS_CANDIDATES]
    assert len(amb) >= 1
    # Ambiguity always involves at least two candidate changes and a narrow
    # score gap between the top two.
    for _, row in amb.iterrows():
        ids = _split_ids(row.candidate_change_ids)
        assert len(ids) >= 2, row
        if row.second_score not in ("", None):
            assert float(row.top_score) - float(row.second_score) <= 0.5 + 1e-9


def test_insufficient_evidence_has_no_confirmed_candidate(triage_results):
    import json as _json

    ins = triage_results[triage_results.reason_code == REASON_INSUFFICIENT_EVIDENCE]
    assert len(ins) >= 1
    for _, row in ins.iterrows():
        # The evidence JSON may list candidates *considered*; what must not
        # exist is a *selected* winner (that would be a TRIAGE).
        evidence = _json.loads(row.evidence) if row.evidence else {}
        assert "selected" not in evidence, row


def test_normal_controls_never_cited_by_triage(triage_results, schema_changes):
    # NORMAL_CHANGE records are negative controls: no triage row may cite one
    # as the candidate explanation of an anomaly.
    normal_ids = set(schema_changes[
        schema_changes.change_category == "NORMAL_CHANGE"]["change_id"])
    triaged = triage_results[triage_results.decision == DECISION_TRIAGE]
    for _, row in triaged.iterrows():
        cited = set(_split_ids(row.candidate_change_ids))
        assert not (cited & normal_ids), row


def test_unknown_anomalies_not_confirmed(triage_results):
    triaged = triage_results[triage_results.decision == DECISION_TRIAGE]
    for _, row in triaged.iterrows():
        cats = set(_split_ids(row.candidate_categories))
        assert "UNKNOWN" not in cats


def test_triage_receipt_and_manifest(triage_run):
    receipt = json.loads((triage_run / "run_receipt.json").read_text())
    for key in ("input_rows", "anomalies_detected", "triage", "abstain"):
        assert key in receipt
    manifest = json.loads((triage_run / "manifest.json").read_text())
    assert manifest["command"] == "p2_triage"
    assert manifest["status"] == "INTERNAL_RESEARCH"


def test_anomalies_csv_schema(triage_run):
    df = pd.read_csv(triage_run / "anomalies.csv", keep_default_na=False)
    for col in ["anomaly_id", "node_id", "rule", "window_start", "window_end"]:
        assert col in df.columns
    assert df["anomaly_id"].is_unique
