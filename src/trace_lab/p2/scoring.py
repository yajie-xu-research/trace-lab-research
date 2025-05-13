"""Transparent rule scoring for candidate changes.

A candidate must pass two required gates — lineage path association and time
validity (both handled by the candidate search) — and is then scored with
fixed frozen weights: symptom-type match, missing-pattern alignment, node
distance penalty, affected-span bonus, and counter-example penalty.

Scores are transparent: every term and its references are recorded in the
candidate evidence so a reviewer can recompute the number by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .categories import CategoryDict
from .candidates import Candidate
from .constants import CHANGE_CATEGORY_TO_DEFECT_CATEGORY
from .lineage import _parse_ts


@dataclass
class ScoredCandidate:
    candidate: Candidate
    category: str
    score: float
    terms: dict[str, Any] = field(default_factory=dict)


def score_candidates(
    candidates: list[Candidate],
    anomaly_rule: str,
    anomaly_time: datetime,
    window_start: str,
    category_dict: CategoryDict,
    weights: dict[str, float],
    anomaly_details: dict[str, Any],
) -> list[ScoredCandidate]:
    scored: list[ScoredCandidate] = []
    ws = _parse_ts(window_start)
    for cand in candidates:
        change_cat = cand.change_category
        defect_cat = CHANGE_CATEGORY_TO_DEFECT_CATEGORY[change_cat]

        # Symptom-type match: the raw signature weight (0..3) scaled by the
        # frozen symptom weight. A change type with no matching signature for
        # this anomaly rule contributes zero and cannot carry the candidate
        # to TRIAGE. NORMAL_CHANGE records are registered negative controls:
        # they carry no evidence of a behavior change and are never used to
        # explain an anomaly (so they can neither be reported as a defect nor
        # tie against a real business change).
        symptom_weight = category_dict.symptom_weight(defect_cat, anomaly_rule)
        is_normal_control = change_cat == "NORMAL_CHANGE"
        if is_normal_control:
            symptom_weight = 0.0
        symptom_points = weights["symptom_type_match"] * symptom_weight
        matched_symptom = symptom_weight > 0

        # Time proximity: a continuous bonus preferring changes effective
        # shortly before the anomaly window start; far changes decay to zero.
        # The decay span matches the candidate lookback (25 days).
        eff = _parse_ts(cand.effective_at)
        days_before = (ws - eff).total_seconds() / 86400.0
        proximity = max(0.0, 1.0 - days_before / 25.0)
        proximity_points = weights["time_proximity_scale"] * proximity

        # Missing-pattern alignment: an extraction-pipeline change aligns with
        # a missing-rate anomaly only if the anomaly window really shows a
        # missing shift (recorded by the detector).
        missing_points = 0.0
        if change_cat == "EXTRACTION_PIPELINE_CHANGE" and anomaly_rule == "MISSING_RATE_SHIFT":
            missing_points = weights["missing_pattern_alignment"]

        # Node distance penalty: distance 0 = change touches the anomaly node.
        distance_penalty = weights["node_distance_penalty_per_hop"] * cand.node_distance

        # Affected-span bonus.
        span_bonus = weights["affected_span_bonus"] if cand.covers_anomaly_node else 0.0

        # Counter-examples: a change of the same type elsewhere on the path
        # whose effective time lies outside the candidate window counts as a
        # counter-example (recorded by the caller via evidence, if present).
        counter_examples = cand.evidence.get("counter_examples", [])
        counter_penalty = weights["counter_example_penalty"] * len(counter_examples)

        score = round(
            weights["lineage_path_association"]
            + weights["time_validity"]
            + symptom_points
            + proximity_points
            + missing_points
            + span_bonus
            - distance_penalty
            - counter_penalty,
            4,
        )

        terms = {
            "lineage_path_association": weights["lineage_path_association"],
            "time_validity": weights["time_validity"],
            "symptom_type_match": symptom_points,
            "symptom_weight_raw": symptom_weight,
            "matched_symptom": matched_symptom,
            "normal_change_control": is_normal_control,
            "time_proximity": round(proximity_points, 4),
            "days_before_window_start": round(days_before, 2),
            "missing_pattern_alignment": missing_points,
            "affected_span_bonus": span_bonus,
            "node_distance_penalty": -distance_penalty,
            "counter_example_penalty": -counter_penalty,
            "total": score,
            "refs": {
                "change_id": cand.change_id,
                "effective_at": cand.effective_at,
                "path": cand.path,
                "counter_examples": counter_examples,
            },
        }
        scored.append(ScoredCandidate(candidate=cand, category=defect_cat, score=score, terms=terms))

    scored.sort(key=lambda s: (-s.score, s.candidate.change_id))
    return scored
