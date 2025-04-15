"""TRACE-LAB triage pipeline.

detect anomalies -> resolve lineage at anomaly time -> search candidate
changes -> transparent rule scoring -> TRIAGE or ABSTAIN.

Ground-truth isolation: this module reads only TRIAGE_INPUT_FILES. Defect
tickets, the perturbation plan, and the normal-control index are never opened
here; the run writer copies them into data/_ground_truth/ for evaluation
without using their content. Deleting them must leave every result file
byte-identical (covered by tests/test_leakage.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..common.hashing import hash_files, hash_object
from ..common.io import read_csv_ordered, read_json, write_csv, write_json
from ..common.log import RunLog
from ..common.manifest import manifest_for_command
from ..common.run_id import logical_utc
from .anomalies import detect_anomalies
from .candidates import search_candidates
from .categories import CategoryDict
from .constants import (
    DECISION_ABSTAIN,
    DECISION_TRIAGE,
    REASON_AMBIGUOUS_CANDIDATES,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_LINEAGE_UNRESOLVED,
    TRIAGE_INPUT_FILES,
    GROUND_TRUTH_FILES,
)
from .lineage import LineageGraph, _parse_ts, _fmt_ts
from .scoring import score_candidates

TRIAGE_NOTE = (
    "TRIAGE recommends human review of the listed candidate changes and "
    "categories. It does not assert that the change caused the anomaly."
)


@dataclass
class TriageOutcome:
    anomaly: dict[str, Any]
    node_id: str
    schema_version: str
    decision: str
    reason_code: str
    candidate_change_ids: list[str]
    candidate_categories: list[str]
    top_score: float | None
    second_score: float | None
    lineage_path: list[str]
    breakpoints: list[str]
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_id": self.anomaly["anomaly_id"],
            "node_id": self.node_id,
            "schema_version": self.schema_version,
            "rule": self.anomaly["rule"],
            "window_start": self.anomaly["window_start"],
            "window_end": self.anomaly["window_end"],
            "decision": self.decision,
            "reason_code": self.reason_code,
            "candidate_change_ids": "|".join(self.candidate_change_ids),
            "candidate_categories": "|".join(self.candidate_categories),
            "top_score": "" if self.top_score is None else self.top_score,
            "second_score": "" if self.second_score is None else self.second_score,
            "lineage_path": "|".join(self.lineage_path),
            "breakpoints": "|".join(self.breakpoints),
            "triage_note": TRIAGE_NOTE if self.decision == DECISION_TRIAGE else "",
            "evidence": json.dumps(self.evidence, sort_keys=True, separators=(",", ":")),
        }


def _anomaly_time(anomaly: dict[str, Any]) -> datetime:
    # The candidate window is anchored at the observation window START: the
    # change must precede the onset of the anomalous period (or begin within
    # the lookahead margin).
    return _parse_ts(anomaly["window_start"])


def load_policy(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_triage(
    input_dir: str | Path,
    out_dir: str | Path,
    categories_config: str | Path,
    policy_config: str | Path,
    *,
    seed: str = "20250110",
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy(policy_config)
    category_dict = CategoryDict.load(categories_config)
    rule_version = policy["rule_version"]
    log = RunLog(out_dir / "run.log", logical_utc("p2_triage"))

    # --- Load permitted inputs only. ---
    nodes = read_csv_ordered(input_dir / "lineage_nodes.csv")
    edges = read_csv_ordered(input_dir / "lineage_edges.csv")
    changes = read_csv_ordered(input_dir / "schema_changes.csv")
    profiles = read_csv_ordered(input_dir / "field_profiles.csv")
    observations = read_csv_ordered(input_dir / "field_observations.csv")

    # The ticket index column of the change register is not used as a
    # feature; it is dropped before candidate construction so that triage
    # cannot see whether a change already has an opened ticket.
    changes = changes.drop(columns=["ticket_index"], errors="ignore")

    graph = LineageGraph(nodes=nodes, edges=edges)

    input_rows = len(observations)

    # --- Exclusions: observation rows whose node is not in the lineage. ---
    known_nodes = set(nodes["node_id"].astype(str))
    orphan_mask = ~observations["node_id"].astype(str).isin(known_nodes)
    excluded = observations[orphan_mask].copy()
    excluded["exclusion_reason"] = "ORPHAN_NODE"
    observations = observations[~orphan_mask].copy()

    # --- Anomaly detection. ---
    anomalies = [a.to_dict() for a in detect_anomalies(observations, profiles, nodes, policy)]
    log.info(f"loaded {input_rows} observation rows; {len(excluded)} orphan rows excluded")

    lookback = int(policy["candidate_search"]["lookback_days"])
    lookahead = int(policy["candidate_search"]["lookahead_days"])
    max_hops = int(policy["candidate_search"]["max_upstream_hops"])
    weights = policy["scoring"]["weights"]
    min_score = float(policy["scoring"]["min_triage_score"])
    tie_epsilon = float(policy["scoring"]["tie_epsilon"])
    ambiguous_days = int(policy["scoring"]["ambiguous_window_days"])

    outcomes: list[TriageOutcome] = []
    for anomaly in anomalies:
        node_id = anomaly["node_id"]
        at = _anomaly_time(anomaly)
        node_row = graph.node(node_id, at)
        schema_version = "" if node_row is None else str(node_row["schema_version"])

        lineage, candidates = search_candidates(
            graph, changes, node_id, at, lookback, lookahead, max_hops
        )

        if not lineage["ok"]:
            outcomes.append(
                TriageOutcome(
                    anomaly=anomaly,
                    node_id=node_id,
                    schema_version=schema_version,
                    decision=DECISION_ABSTAIN,
                    reason_code=REASON_LINEAGE_UNRESOLVED,
                    candidate_change_ids=[],
                    candidate_categories=[],
                    top_score=None,
                    second_score=None,
                    lineage_path=lineage["path"],
                    breakpoints=lineage["breakpoints"],
                    evidence={
                        "lineage_failure": lineage["failure"],
                        "details": lineage["details"],
                    },
                )
            )
            continue

        scored = score_candidates(
            candidates, anomaly["rule"], at, anomaly["window_start"], category_dict, weights, anomaly["details"]
        )

        # Required symptom-type gate: a candidate whose change type does not
        # match the anomaly rule's signature cannot be triaged.
        eligible = [s for s in scored if s.terms["matched_symptom"] and s.score >= min_score]

        if not eligible:
            outcomes.append(
                TriageOutcome(
                    anomaly=anomaly,
                    node_id=node_id,
                    schema_version=schema_version,
                    decision=DECISION_ABSTAIN,
                    reason_code=REASON_INSUFFICIENT_EVIDENCE,
                    candidate_change_ids=[s.candidate.change_id for s in scored[:3]],
                    candidate_categories=[s.category for s in scored[:3]],
                    top_score=scored[0].score if scored else None,
                    second_score=None,
                    lineage_path=lineage["path"],
                    breakpoints=[],
                    evidence={
                        "candidates_considered": [
                            {"change_id": s.candidate.change_id, "category": s.category, "score": s.score}
                            for s in scored[:5]
                        ]
                    },
                )
            )
            continue

        top = eligible[0]
        # Ambiguity: another eligible candidate whose change differs and whose
        # score is within tie_epsilon and whose effective time is within the
        # ambiguity span of the top candidate.
        ambiguous: list[Any] = []
        for other in eligible[1:]:
            if other.candidate.change_id == top.candidate.change_id:
                continue
            delta = abs(_parse_ts(other.candidate.effective_at) - _parse_ts(top.candidate.effective_at))
            if top.score - other.score <= tie_epsilon and delta <= timedelta(days=ambiguous_days):
                ambiguous.append(other)

        if ambiguous:
            tied = [top] + ambiguous
            outcomes.append(
                TriageOutcome(
                    anomaly=anomaly,
                    node_id=node_id,
                    schema_version=schema_version,
                    decision=DECISION_ABSTAIN,
                    reason_code=REASON_AMBIGUOUS_CANDIDATES,
                    candidate_change_ids=[s.candidate.change_id for s in tied],
                    candidate_categories=sorted({s.category for s in tied}),
                    top_score=top.score,
                    second_score=ambiguous[0].score,
                    lineage_path=lineage["path"],
                    breakpoints=[],
                    evidence={
                        "tied_candidates": [
                            {
                                "change_id": s.candidate.change_id,
                                "category": s.category,
                                "score": s.score,
                                "effective_at": s.candidate.effective_at,
                            }
                            for s in tied
                        ]
                    },
                )
            )
            continue

        second_score = eligible[1].score if len(eligible) > 1 else None
        outcomes.append(
            TriageOutcome(
                anomaly=anomaly,
                node_id=node_id,
                schema_version=schema_version,
                decision=DECISION_TRIAGE,
                reason_code="",
                candidate_change_ids=[top.candidate.change_id],
                candidate_categories=[top.category],
                top_score=top.score,
                second_score=second_score,
                lineage_path=lineage["path"],
                breakpoints=[],
                evidence={
                    "selected": {
                        "change_id": top.candidate.change_id,
                        "category": top.category,
                        "score": top.score,
                        "terms": top.terms,
                        "path": top.candidate.path,
                        "affected_nodes": top.candidate.affected_nodes,
                    },
                    "runner_up": (
                        {
                            "change_id": eligible[1].candidate.change_id,
                            "category": eligible[1].category,
                            "score": eligible[1].score,
                        }
                        if len(eligible) > 1
                        else None
                    ),
                    "supporting_source_indices": {
                        "change_ids": [top.candidate.change_id],
                        "lineage_edges": lineage["edges"],
                        "raw_observation_indices": anomaly["raw_indices"],
                    },
                },
            )
        )

    # --- Write results. ---
    results_df = pd.DataFrame([o.to_dict() for o in outcomes])
    results_df.to_csv(out_dir / "triage_results.csv", index=False)
    anomalies_df = pd.DataFrame(anomalies)
    anomalies_df.to_csv(out_dir / "anomalies.csv", index=False)
    if excluded.empty:
        pd.DataFrame(columns=["observation_id", "node_id", "exclusion_reason"]).to_csv(
            out_dir / "excluded_rows.csv", index=False
        )
    else:
        excluded.to_csv(out_dir / "excluded_rows.csv", index=False)

    triage_count = int((results_df["decision"] == DECISION_TRIAGE).sum()) if not results_df.empty else 0
    abstain_count = int((results_df["decision"] == DECISION_ABSTAIN).sum()) if not results_df.empty else 0
    reason_counts = {}
    if not results_df.empty:
        abstain_rows = results_df[results_df["decision"] == DECISION_ABSTAIN]
        reason_counts = abstain_rows.groupby("reason_code").size().to_dict()

    # --- Ground truth copy (evaluation only; content never touches triage). ---
    # If the ground-truth inputs are absent, the copy and label build are
    # skipped; the triage outputs themselves do not change either way.
    gt_dir = out_dir / "data" / "_ground_truth"
    import shutil

    gt_present = all((input_dir / f).exists() for f in GROUND_TRUTH_FILES)
    if gt_present:
        gt_dir.mkdir(parents=True, exist_ok=True)
        for fname in GROUND_TRUTH_FILES:
            shutil.copyfile(input_dir / fname, gt_dir / fname)
        _build_true_defect_labels(input_dir).to_csv(gt_dir / "true_defect_labels.csv", index=False)

    # --- Input hashes for reproducibility. ---
    input_hashes = []
    for fname in sorted(TRIAGE_INPUT_FILES):
        path = input_dir / fname
        if path.exists():
            from ..common.hashing import hash_file

            input_hashes.append({"file": fname, "sha256": hash_file(path)})
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(input_hashes).to_csv(out_dir / "data" / "input_hashes.csv", index=False)

    # --- Receipt. ---
    receipt = {
        "input_dir": str(input_dir),
        "input_rows": input_rows,
        "orphan_rows_excluded": int(len(excluded)),
        "anomalies_detected": len(anomalies),
        "triage": triage_count,
        "abstain": abstain_count,
        "abstain_by_reason": {k: int(v) for k, v in reason_counts.items()},
        "node_versions_seen": sorted(set(o.schema_version for o in outcomes)),
    }
    write_json(receipt, out_dir / "run_receipt.json")

    # --- Manifest. ---
    config_hash = hash_files([str(categories_config), str(policy_config)])
    data_hash = hash_files([str(input_dir / f) for f in TRIAGE_INPUT_FILES if (input_dir / f).exists()])
    results_hash = hash_files([str(out_dir / "triage_results.csv"), str(out_dir / "anomalies.csv")])
    manifest = manifest_for_command(
        "p2_triage",
        config_hash=config_hash,
        data_hash=data_hash,
        seed=seed,
        rule_version=rule_version,
        results_hash=results_hash,
        input_rows=input_rows,
        excluded_rows=int(len(excluded)),
        known_issues=[
            "Anomaly detection windows are fixed-width and overlap; one "
            "underlying change can produce more than one anomaly row.",
            "TRIAGE is advisory; it does not confirm causality.",
        ],
    )
    write_json(manifest, out_dir / "manifest.json")

    log.info(f"anomalies={len(anomalies)} triage={triage_count} abstain={abstain_count}")
    log.info(f"manifest result_hash={manifest['result_hash']}")
    log.close()

    return {"manifest": manifest, "receipt": receipt, "out_dir": str(out_dir)}


def _build_true_defect_labels(input_dir: Path) -> pd.DataFrame:
    """Build the evaluation label file from the perturbation plan.

    Called by the run writer only; the triage pipeline itself never reads
    these inputs (the leakage test proves it).
    """
    plan = read_json(input_dir / "perturbation_library.json")
    rows = []
    for p in plan["perturbations"]:
        rows.append(
            {
                "perturbation_id": p["perturbation_id"],
                "defect_id": p["defect_id"],
                "node_id": p["node_id"],
                "true_category": p["true_category"],
                "change_id": p.get("change_id", ""),
                "window_start": p["window_start"],
                "window_end": p["window_end"],
                "ambiguous_pair": p.get("ambiguous_pair", ""),
                "lineage_break": bool(p.get("lineage_break", False)),
            }
        )
    return pd.DataFrame(rows)
