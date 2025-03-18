"""Lineage graph, candidate search, and anomaly-detection contract tests."""

from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone

import pandas as pd
import pytest

from trace_lab.p2.anomalies import Anomaly, detect_anomalies
from trace_lab.p2.candidates import search_candidates
from trace_lab.p2.lineage import LineageGraph, valid_at
from trace_lab.p2.constants import SCHEMA_V1

V1_TIME = datetime(2025, 3, 15, tzinfo=timezone.utc)
V2_TIME = datetime(2026, 3, 15, tzinfo=timezone.utc)


def _graph(lineage_nodes, lineage_edges) -> LineageGraph:
    return LineageGraph(nodes=lineage_nodes, edges=lineage_edges)


def _parse(ts: str) -> datetime:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def test_valid_at_semantics():
    assert valid_at("2025-01-01T00:00:00Z", "", datetime(2025, 6, 1, tzinfo=timezone.utc))
    assert not valid_at("2025-06-01T00:00:00Z", "", datetime(2025, 5, 1, tzinfo=timezone.utc))
    assert valid_at("2025-01-01T00:00:00Z", "2025-06-01T00:00:00Z",
                    datetime(2025, 5, 31, tzinfo=timezone.utc))
    assert not valid_at("2025-01-01T00:00:00Z", "2025-06-01T00:00:00Z",
                        datetime(2025, 6, 1, tzinfo=timezone.utc))


def test_node_lookup_respects_version(lineage_nodes, lineage_edges):
    g = _graph(lineage_nodes, lineage_edges)
    n = g.node("N005", V1_TIME)
    assert n is not None and n["schema_version"] == SCHEMA_V1
    assert g.node("N005", V2_TIME) is None
    assert g.node("N019", V2_TIME) is not None
    assert g.node("N019", V1_TIME) is None


def test_upstream_path_v2_report_chain(lineage_nodes, lineage_edges):
    g = _graph(lineage_nodes, lineage_edges)
    res = g.upstream_path("N019", V2_TIME, max_hops=8)
    assert res["ok"]
    assert res["path"][-1] == "N019"
    assert "N001" in res["path"]            # source node
    assert len(res["path"]) >= 5
    # Path is a chain: consecutive pairs must be edges.
    for a, b in zip(res["path"], res["path"][1:]):
        incoming = g._edges_from(b, V2_TIME)
        assert len(incoming[incoming.from_node == a]) == 1


def test_lineage_breakpoint_on_reagent_chain(lineage_nodes, lineage_edges):
    g = _graph(lineage_nodes, lineage_edges)
    before = datetime(2025, 12, 15, tzinfo=timezone.utc)
    after = datetime(2026, 1, 15, tzinfo=timezone.utc)
    res_before = g.upstream_path("N029", before, max_hops=8)
    res_after = g.upstream_path("N029", after, max_hops=8)
    assert res_before["ok"]
    # After the N030->N029 edge expires the path is broken at N029.
    assert not res_after["ok"]
    assert res_after["failure"] == "break"
    assert res_after["breakpoints"]


def test_search_candidates_respects_window(lineage_nodes, lineage_edges, schema_changes):
    g = _graph(lineage_nodes, lineage_edges)
    lineage, candidates = search_candidates(
        g, schema_changes, anomaly_node="N019", anomaly_time=V2_TIME,
        lookback_days=25, lookahead_days=21, max_upstream_hops=8)
    lo = V2_TIME - dt.timedelta(days=25)
    hi = V2_TIME + dt.timedelta(days=21)
    assert lineage["ok"]
    for c in candidates:
        assert lo <= _parse(c.effective_at) <= hi, c


def test_search_candidates_only_on_path(lineage_nodes, lineage_edges, schema_changes):
    g = _graph(lineage_nodes, lineage_edges)
    lineage, candidates = search_candidates(
        g, schema_changes, anomaly_node="N019", anomaly_time=V2_TIME,
        lookback_days=25, lookahead_days=21, max_upstream_hops=8)
    path_ids = set(lineage["path"])
    for c in candidates:
        assert c.affected_nodes and set(c.affected_nodes) & path_ids, c


def test_search_candidates_on_broken_lineage(lineage_nodes, lineage_edges, schema_changes):
    g = _graph(lineage_nodes, lineage_edges)
    at = datetime(2026, 1, 15, tzinfo=timezone.utc)
    lineage, candidates = search_candidates(
        g, schema_changes, anomaly_node="N029", anomaly_time=at,
        lookback_days=25, lookahead_days=21, max_upstream_hops=8)
    assert not lineage["ok"]
    assert candidates == []


def test_anomaly_dataclass_roundtrip():
    a = Anomaly(
        anomaly_id="AN-1", node_id="N019", rule="CHANGE_POINT",
        window_start="2026-01-01T00:00:00Z", window_end="2026-01-29T00:00:00Z",
        raw_indices=[1, 2, 3], n_observations=3, details={"z": 5.2})
    d = a.to_dict()
    assert d["anomaly_id"] == "AN-1"
    assert d["raw_indices"] == [1, 2, 3]
    assert d["details"]["z"] == 5.2


def test_detection_produces_all_five_rule_kinds(synthetic, lineage_nodes, config_paths):
    import yaml

    obs = pd.read_csv(synthetic / "field_observations.csv", keep_default_na=False)
    profiles = pd.read_csv(synthetic / "field_profiles.csv", keep_default_na=False)
    with open(config_paths["policy"]) as fh:
        policy = yaml.safe_load(fh)
    anomalies = detect_anomalies(obs, profiles, lineage_nodes, policy)
    kinds = {a.rule for a in anomalies}
    assert kinds == {"FORMAT_VIOLATION", "RANGE_VIOLATION", "UNIT_DEVIATION",
                     "MISSING_RATE_SHIFT", "CHANGE_POINT"}
