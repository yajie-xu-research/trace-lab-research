"""Rule-based comparison baselines.

Four baselines run on the same anomaly set as the TRACE-LAB method:
- B0: single-field format/range/unit rules with a fixed rule->category map;
- B1: same detector, nearest change in time, no lineage constraint;
- B2: ordinary change-point detection, nearest change regardless of type;
- B3: static site-specific (system, rule) -> category mapping table.

Each baseline returns rows in the same shape as triage results so the
evaluation can compare them on identical ground truth.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .constants import (
    CHANGE_CATEGORY_TO_DEFECT_CATEGORY,
    DECISION_ABSTAIN,
    DECISION_TRIAGE,
    REASON_INSUFFICIENT_EVIDENCE,
)
from .lineage import _parse_ts

B0_RULE_TO_CATEGORY = {
    "FORMAT_VIOLATION": "INTERFACE_MAPPING_ERROR",
    "RANGE_VIOLATION": "UNIT_CHANGE",
    "UNIT_DEVIATION": "UNIT_CHANGE",
    "MISSING_RATE_SHIFT": "EXTRACTION_FAILURE",
    "CHANGE_POINT": "FIELD_SEMANTIC_CHANGE",
}


def _result_row(anomaly: dict[str, Any], decision: str, reason: str, categories: list[str], changes: list[str]) -> dict[str, Any]:
    return {
        "anomaly_id": anomaly["anomaly_id"],
        "node_id": anomaly["node_id"],
        "rule": anomaly["rule"],
        "window_start": anomaly["window_start"],
        "window_end": anomaly["window_end"],
        "decision": decision,
        "reason_code": reason,
        "candidate_change_ids": "|".join(changes),
        "candidate_categories": "|".join(categories),
    }


def baseline_b0(anomalies: list[dict[str, Any]]) -> pd.DataFrame:
    """Single-field rules: fixed rule->category map, no lineage, no abstain."""
    rows = []
    for anomaly in anomalies:
        category = B0_RULE_TO_CATEGORY[anomaly["rule"]]
        rows.append(_result_row(anomaly, DECISION_TRIAGE, "", [category], []))
    return pd.DataFrame(rows)


def _nearest_change(anomaly: dict[str, Any], changes: pd.DataFrame, lookback_days: int) -> dict[str, Any] | None:
    start = _parse_ts(anomaly["window_start"]) - timedelta(days=lookback_days)
    end = _parse_ts(anomaly["window_end"])
    best = None
    best_delta = None
    for _, row in changes.iterrows():
        eff = _parse_ts(str(row["effective_at"]))
        if eff is None or not (start <= eff <= end):
            continue
        delta = abs((eff - end).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = row
    return None if best is None else best.to_dict()


def baseline_b1(anomalies: list[dict[str, Any]], changes: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """Same detector, no lineage: nearest change in time regardless of path."""
    rows = []
    for anomaly in anomalies:
        nearest = _nearest_change(anomaly, changes, lookback_days)
        if nearest is None:
            rows.append(_result_row(anomaly, DECISION_ABSTAIN, REASON_INSUFFICIENT_EVIDENCE, [], []))
            continue
        category = CHANGE_CATEGORY_TO_DEFECT_CATEGORY[str(nearest["change_category"])]
        rows.append(
            _result_row(anomaly, DECISION_TRIAGE, "", [category], [str(nearest["change_id"])])
        )
    return pd.DataFrame(rows)


def baseline_b2(anomalies: list[dict[str, Any]], changes: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    """Ordinary change-point detection only; nearest change regardless of type."""
    rows = []
    for anomaly in anomalies:
        if anomaly["rule"] != "CHANGE_POINT":
            rows.append(_result_row(anomaly, DECISION_ABSTAIN, REASON_INSUFFICIENT_EVIDENCE, [], []))
            continue
        nearest = _nearest_change(anomaly, changes, lookback_days)
        if nearest is None:
            rows.append(_result_row(anomaly, DECISION_ABSTAIN, REASON_INSUFFICIENT_EVIDENCE, [], []))
            continue
        category = CHANGE_CATEGORY_TO_DEFECT_CATEGORY[str(nearest["change_category"])]
        rows.append(
            _result_row(anomaly, DECISION_TRIAGE, "", [category], [str(nearest["change_id"])])
        )
    return pd.DataFrame(rows)


def baseline_b3(
    anomalies: list[dict[str, Any]],
    nodes: pd.DataFrame,
    baseline_config: str | Path,
) -> pd.DataFrame:
    """Static site-specific (system, rule) mapping table."""
    with open(baseline_config, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    table = {
        (entry["system"], entry["anomaly_rule"]): entry["category"]
        for entry in config["mapping"]
    }
    system_of_node = dict(zip(nodes["node_id"].astype(str), nodes["system"].astype(str)))
    rows = []
    for anomaly in anomalies:
        system = system_of_node.get(anomaly["node_id"], "UNKNOWN")
        category = table.get((system, anomaly["rule"]))
        if category is None:
            rows.append(_result_row(anomaly, DECISION_ABSTAIN, REASON_INSUFFICIENT_EVIDENCE, [], []))
            continue
        rows.append(_result_row(anomaly, DECISION_TRIAGE, "", [category], []))
    return pd.DataFrame(rows)
