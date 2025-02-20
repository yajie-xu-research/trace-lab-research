"""Versioned field lineage graph.

Nodes and edges carry valid_from/valid_to validity ranges. All queries take
an ``at`` timestamp and consider only nodes/edges valid at that instant.

Resolution failures:
- break: a node on the upstream path has no valid incoming edge (or an edge
  points at a node that is not valid at ``at``);
- cycle: the walk revisits a node;
- contradiction: two edges for the same (from_node, to_node) overlap in time
  with different transform_id/rule_version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _parse_ts(value: str) -> datetime | None:
    if not value or str(value).strip() == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _fmt_ts(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_at(valid_from: str, valid_to: str, at: datetime) -> bool:
    start = _parse_ts(valid_from)
    end = _parse_ts(valid_to)
    if start is None:
        return False
    if start > at:
        return False
    if end is not None and end <= at:
        return False
    return True


@dataclass
class LineageGraph:
    nodes: pd.DataFrame
    edges: pd.DataFrame

    @classmethod
    def load(cls, nodes_csv: str, edges_csv: str) -> "LineageGraph":
        nodes = pd.read_csv(nodes_csv, keep_default_na=False)
        edges = pd.read_csv(edges_csv, keep_default_na=False)
        return cls(nodes=nodes, edges=edges)

    def node(self, node_id: str, at: datetime) -> dict[str, Any] | None:
        rows = self.nodes[self.nodes["node_id"] == node_id]
        for _, row in rows.iterrows():
            if valid_at(row["valid_from"], row["valid_to"], at):
                return row.to_dict()
        return None

    def _edges_from(self, node_id: str, at: datetime) -> pd.DataFrame:
        mask = self.edges["to_node"] == node_id
        sub = self.edges[mask]
        return sub[
            sub.apply(lambda r: valid_at(r["valid_from"], r["valid_to"], at), axis=1)
        ]

    def validate_contradictions(self, at: datetime) -> list[dict[str, str]]:
        """Find overlapping edges with conflicting transform versions."""
        conflicts: list[dict[str, str]] = []
        pairs = self.edges.groupby(["from_node", "to_node"])
        for (frm, to), group in pairs:
            rows = list(group.itertuples())
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    a, b = rows[i], rows[j]
                    a_from, a_to = _parse_ts(a.valid_from), _parse_ts(a.valid_to)
                    b_from, b_to = _parse_ts(b.valid_from), _parse_ts(b.valid_to)
                    if a_from is None or b_from is None:
                        continue
                    a_end = a_to or datetime(2999, 1, 1, tzinfo=timezone.utc)
                    b_end = b_to or datetime(2999, 1, 1, tzinfo=timezone.utc)
                    if a_from <= b_end and b_from <= a_end:
                        if a.transform_id != b.transform_id or a.rule_version != b.rule_version:
                            conflicts.append(
                                {
                                    "from_node": frm,
                                    "to_node": to,
                                    "edge_a": f"{a.transform_id}@{a.rule_version}",
                                    "edge_b": f"{b.transform_id}@{b.rule_version}",
                                }
                            )
        return conflicts

    def upstream_path(
        self, node_id: str, at: datetime, max_hops: int = 8
    ) -> dict[str, Any]:
        """Walk upstream from node_id at time ``at``.

        Returns a dict with ``ok``, ``path`` (list of node ids from upstream to
        downstream), ``edges`` (list of edge dicts), ``breakpoints`` (list of
        node ids where the chain stops), and ``failure`` in {None, 'break',
        'cycle', 'contradiction'}.
        """
        conflicts = self.validate_contradictions(at)
        if conflicts:
            return {
                "ok": False,
                "failure": "contradiction",
                "path": [],
                "edges": [],
                "breakpoints": [],
                "details": conflicts,
            }

        current = self.node(node_id, at)
        if current is None:
            return {
                "ok": False,
                "failure": "break",
                "path": [],
                "edges": [],
                "breakpoints": [node_id],
                "details": f"node {node_id} is not valid at {_fmt_ts(at)}",
            }

        path = [node_id]
        edges_found: list[dict[str, Any]] = []
        visited: set[str] = set()
        breakpoints: list[str] = []

        # A node is a true source only if no edge ever points to it in the
        # whole table. If edges exist but none is valid at ``at``, the chain
        # is broken.
        ever_targeted = set(self.edges["to_node"].astype(str))

        while len(path) <= max_hops:
            visited.add(path[0])
            incoming = self._edges_from(path[0], at)
            if incoming.empty:
                if path[0] in ever_targeted:
                    return {
                        "ok": False,
                        "failure": "break",
                        "path": path,
                        "edges": edges_found,
                        "breakpoints": breakpoints + [path[0]],
                        "details": (
                            f"node {path[0]} expects upstream input but no "
                            f"incoming edge is valid at {_fmt_ts(at)}"
                        ),
                    }
                break  # reached a source node
            # Take the first valid incoming edge deterministically.
            row = incoming.sort_values(
                ["from_node", "transform_id", "rule_version"]
            ).iloc[0]
            from_node = str(row["from_node"])
            if from_node in visited:
                return {
                    "ok": False,
                    "failure": "cycle",
                    "path": path,
                    "edges": edges_found,
                    "breakpoints": breakpoints,
                    "details": f"cycle via node {from_node}",
                }
            upstream = self.node(from_node, at)
            if upstream is None:
                return {
                    "ok": False,
                    "failure": "break",
                    "path": path,
                    "edges": edges_found,
                    "breakpoints": breakpoints + [from_node],
                    "details": (
                        f"edge {from_node} -> {path[0]} exists but node "
                        f"{from_node} is not valid at {_fmt_ts(at)}"
                    ),
                }
            edges_found.append(
                {
                    "from_node": from_node,
                    "to_node": str(row["to_node"]),
                    "transform_id": str(row["transform_id"]),
                    "rule_version": str(row["rule_version"]),
                    "valid_from": str(row["valid_from"]),
                    "valid_to": str(row["valid_to"]),
                    "confirmed_by": str(row["confirmed_by"]),
                    "source_file": str(row["source_file"]),
                }
            )
            path.insert(0, from_node)

        return {
            "ok": True,
            "failure": None,
            "path": path,
            "edges": edges_found,
            "breakpoints": breakpoints,
            "details": None,
        }
