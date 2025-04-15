"""Candidate change search.

For an anomaly on a node at time T: resolve the upstream lineage path at T,
then find schema changes whose effective_at falls inside the candidate
window (T - lookback .. T + lookahead) and whose affected_nodes intersect
the path. Candidate features: change effective time, node distance along the
path, change type, affected field span, and alignment of the anomaly's
missing pattern with extraction-pipeline changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .lineage import LineageGraph, _parse_ts, _fmt_ts


@dataclass
class Candidate:
    change_id: str
    change_category: str
    effective_at: str
    node_distance: int
    affected_nodes: list[str]
    covers_anomaly_node: bool
    path: list[str]
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "change_category": self.change_category,
            "effective_at": self.effective_at,
            "node_distance": self.node_distance,
            "affected_nodes": self.affected_nodes,
            "covers_anomaly_node": self.covers_anomaly_node,
            "path": self.path,
            "evidence": self.evidence,
        }


def _split_nodes(value: str) -> list[str]:
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def search_candidates(
    graph: LineageGraph,
    changes: pd.DataFrame,
    anomaly_node: str,
    anomaly_time: datetime,
    lookback_days: int,
    lookahead_days: int,
    max_upstream_hops: int,
) -> tuple[dict[str, Any], list[Candidate]]:
    """Return (lineage_result, candidates)."""
    lineage = graph.upstream_path(anomaly_node, anomaly_time, max_hops=max_upstream_hops)
    if not lineage["ok"]:
        return lineage, []
    path = lineage["path"]
    distance = {node_id: idx for idx, node_id in enumerate(path)}

    window_start = anomaly_time - timedelta(days=lookback_days)
    window_end = anomaly_time + timedelta(days=lookahead_days)

    candidates: list[Candidate] = []
    for _, row in changes.iterrows():
        effective = _parse_ts(str(row["effective_at"]))
        if effective is None:
            continue
        if not (window_start <= effective <= window_end):
            continue
        affected = _split_nodes(str(row["affected_nodes"]))
        overlap = [n for n in affected if n in distance]
        if not overlap:
            continue
        min_distance = min(distance[n] for n in overlap)
        candidates.append(
            Candidate(
                change_id=str(row["change_id"]),
                change_category=str(row["change_category"]),
                effective_at=_fmt_ts(effective),
                node_distance=min_distance,
                affected_nodes=affected,
                covers_anomaly_node=anomaly_node in affected,
                path=path,
                evidence={
                    "lineage_path": path,
                    "lineage_edges": lineage["edges"],
                    "overlap_nodes": overlap,
                    "ticket_index": str(row.get("ticket_index", "")),
                },
            )
        )

    candidates.sort(key=lambda c: (abs((_parse_ts(c.effective_at) - anomaly_time).total_seconds()), c.node_distance, c.change_id))
    return lineage, candidates
