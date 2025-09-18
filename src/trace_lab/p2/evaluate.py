"""Blind perturbation evaluation.

Reads a triage run directory and the ground truth held under
data/_ground_truth/, then computes per-category precision/recall, abstain
rate, false-positive rate on negative controls, and error rows. The four
baselines are re-run on the same anomaly set and evaluated identically.

Ground truth is read here, and only here: the evaluation is the labeled
assessment step, not a feature source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.hashing import hash_files
from ..common.io import read_csv_ordered, read_json, write_csv, write_json
from ..common.log import RunLog
from ..common.manifest import manifest_for_command
from ..common.run_id import logical_utc
from .baselines import baseline_b0, baseline_b1, baseline_b2, baseline_b3
from .categories import CategoryDict
from .constants import (
    BASELINE_IDS,
    CATEGORIES,
    DECISION_ABSTAIN,
    DECISION_TRIAGE,
    REASON_AMBIGUOUS_CANDIDATES,
    REASON_LINEAGE_UNRESOLVED,
)
from .lineage import _parse_ts

DEFECT_CATEGORIES = [c for c in CATEGORIES if c not in ("TRUE_BUSINESS_CHANGE", "UNKNOWN")]


def _overlap_days(a_start: str, a_end: str, b_start: str, b_end: str) -> float:
    a_s, a_e = _parse_ts(a_start), _parse_ts(a_end)
    b_s, b_e = _parse_ts(b_start), _parse_ts(b_end)
    start = max(a_s, b_s)
    end = min(a_e, b_e)
    return max(0.0, (end - start).total_seconds() / 86400.0)


def _match_perturbation(row: dict[str, Any], perturbations: list[dict[str, Any]]) -> dict[str, Any] | None:
    best = None
    best_overlap = 0.0
    for p in perturbations:
        if p["node_id"] != row["node_id"]:
            continue
        overlap = _overlap_days(row["window_start"], row["window_end"], p["window_start"], p["window_end"])
        if overlap >= 1.0 and overlap > best_overlap:
            best_overlap = overlap
            best = p
    return best


def _match_control(row: dict[str, Any], controls: list[dict[str, Any]]) -> dict[str, Any] | None:
    best = None
    best_overlap = 0.0
    for c in controls:
        if c["node_id"] != row["node_id"]:
            continue
        overlap = _overlap_days(row["window_start"], row["window_end"], c["window_start"], c["window_end"])
        if overlap >= 1.0 and overlap > best_overlap:
            best_overlap = overlap
            best = c
    return best


def _split(value: Any) -> list[str]:
    text = str(value)
    if not text:
        return []
    return [part for part in text.split("|") if part]


def evaluate_method(
    results: pd.DataFrame, perturbations: list[dict[str, Any]], controls: list[dict[str, Any]]
) -> dict[str, Any]:
    total_rows = len(results)
    triage_rows = int((results["decision"] == DECISION_TRIAGE).sum())
    abstain_rows = int((results["decision"] == DECISION_ABSTAIN).sum())

    evaluable = [p for p in perturbations if not p.get("ambiguous_pair") and not p.get("lineage_break") and p["true_category"] != "UNKNOWN"]
    ambiguous_set = [p for p in perturbations if p.get("ambiguous_pair")]
    broken_set = [p for p in perturbations if p.get("lineage_break")]
    unknown_set = [p for p in perturbations if p["true_category"] == "UNKNOWN"]

    # Per-category counts (perturbation level).
    category_tp = {c: 0 for c in CATEGORIES}
    category_total = {c: 0 for c in CATEGORIES}
    for p in evaluable:
        category_total[p["true_category"]] += 1

    # Row-level precision counts.
    category_rows_tp = {c: 0 for c in CATEGORIES}
    category_rows_total = {c: 0 for c in CATEGORIES}

    detected_perturbation_ids = set()
    detected_per_category: dict[str, set[str]] = {c: set() for c in CATEGORIES}
    matched_perturbation_ids = set()
    ambiguous_correct = 0
    broken_correct = 0
    unknown_correct = 0
    misattribution_rows = 0
    fp_control_rows = 0
    control_overlap_rows = 0
    unmatched_rows = 0
    triage_on_unknown = 0

    for _, row in results.iterrows():
        row_dict = row.to_dict()
        cats = _split(row_dict["candidate_categories"])
        is_triage = row_dict["decision"] == DECISION_TRIAGE
        reason = str(row_dict["reason_code"])

        p = _match_perturbation(row_dict, perturbations)
        c = _match_control(row_dict, controls)

        if is_triage:
            for cat in cats:
                category_rows_total[cat] += 1

        if c is not None and not p:
            control_overlap_rows += 1
            if is_triage and any(cat in DEFECT_CATEGORIES for cat in cats):
                fp_control_rows += 1
            continue

        if p is None:
            unmatched_rows += 1
            continue

        matched_perturbation_ids.add(p["perturbation_id"])

        if p in ambiguous_set or p.get("ambiguous_pair"):
            if not is_triage and reason == REASON_AMBIGUOUS_CANDIDATES:
                ambiguous_correct += 1
            continue

        if p in broken_set or p.get("lineage_break"):
            if not is_triage and reason == REASON_LINEAGE_UNRESOLVED:
                broken_correct += 1
            continue

        if p["true_category"] == "UNKNOWN":
            if is_triage:
                triage_on_unknown += 1
            else:
                unknown_correct += 1
            continue

        # Evaluable defect perturbation.
        if is_triage:
            true_cat = p["true_category"]
            if true_cat in cats:
                category_rows_tp[true_cat] += 1
                detected_perturbation_ids.add(p["perturbation_id"])
                detected_per_category[true_cat].add(p["perturbation_id"])
            else:
                misattribution_rows += 1

    recall = {
        c: (len(detected_per_category[c]) / category_total[c] if category_total[c] else None)
        for c in CATEGORIES
    }
    precision = {
        c: (category_rows_tp[c] / category_rows_total[c] if category_rows_total[c] else None)
        for c in CATEGORIES
    }

    negative_controls = len(controls)
    return {
        "total_anomaly_rows": total_rows,
        "triage_rows": triage_rows,
        "abstain_rows": abstain_rows,
        "abstain_rate": round(abstain_rows / total_rows, 4) if total_rows else None,
        "evaluable_perturbations": len(evaluable),
        "ambiguous_perturbations": len(ambiguous_set),
        "ambiguous_correctly_abstained": ambiguous_correct,
        "lineage_broken_perturbations": len(broken_set),
        "lineage_broken_correctly_abstained": broken_correct,
        "unknown_perturbations": len(unknown_set),
        "unknown_correctly_abstained": unknown_correct,
        "unknown_mis_triaged": triage_on_unknown,
        "detected_perturbations": len(detected_perturbation_ids),
        "misattribution_rows": misattribution_rows,
        "negative_controls": negative_controls,
        "control_overlap_rows": control_overlap_rows,
        "false_positive_rows_on_controls": fp_control_rows,
        "false_positive_rate_on_controls": (
            round(fp_control_rows / control_overlap_rows, 4) if control_overlap_rows else None
        ),
        "unmatched_anomaly_rows": unmatched_rows,
        "per_category_precision": {k: (round(v, 4) if v is not None else None) for k, v in precision.items()},
        "per_category_recall": {k: (round(v, 4) if v is not None else None) for k, v in recall.items()},
    }


def run_evaluation(
    run_dir: str | Path,
    out_dir: str | Path,
    *,
    policy_config: str | Path,
    baseline_config: str | Path,
    seed: str = "20250110",
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log = RunLog(out_dir / "run.log", logical_utc("p2_evaluate"))
    gt_dir = run_dir / "data" / "_ground_truth"
    for required in ("true_defect_labels.csv", "perturbation_library.json", "normal_control_index.csv"):
        if not (gt_dir / required).exists():
            raise FileNotFoundError(f"ground truth missing in run directory: {required}")

    results = read_csv_ordered(run_dir / "triage_results.csv")
    anomalies = read_csv_ordered(run_dir / "anomalies.csv")
    plan = read_json(gt_dir / "perturbation_library.json")
    perturbations = plan["perturbations"]
    controls_raw = read_csv_ordered(gt_dir / "normal_control_index.csv")
    controls = controls_raw.to_dict(orient="records")

    # Baselines re-run on the same anomalies, using the lineage inputs.
    input_hashes = read_csv_ordered(run_dir / "data" / "input_hashes.csv")
    input_map = dict(zip(input_hashes["file"], input_hashes["sha256"]))

    nodes = read_csv_ordered(_locate_input(run_dir, input_map, "lineage_nodes.csv"))
    changes = read_csv_ordered(_locate_input(run_dir, input_map, "schema_changes.csv"))
    import yaml

    with open(policy_config, "r", encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    window_days = int(policy["candidate_search"]["lookback_days"])

    anomaly_dicts = anomalies.to_dict(orient="records")

    baseline_frames = {
        "B0_SINGLE_FIELD_RULES": baseline_b0(anomaly_dicts),
        "B1_NO_LINEAGE_DETECTION": baseline_b1(anomaly_dicts, changes, window_days),
        "B2_CHANGE_POINT_ONLY": baseline_b2(anomaly_dicts, changes, window_days),
        "B3_SITE_MAPPING_TABLE": baseline_b3(anomaly_dicts, nodes, baseline_config),
    }

    metrics = {"TRACE_LAB_MAIN": evaluate_method(results, perturbations, controls)}
    for baseline_id in BASELINE_IDS:
        metrics[baseline_id] = evaluate_method(baseline_frames[baseline_id], perturbations, controls)

    write_json(metrics, out_dir / "evaluation_report.json")

    baseline_rows = []
    for method, m in metrics.items():
        row = {"method": method}
        for key in ("abstain_rate", "false_positive_rate_on_controls", "misattribution_rows"):
            row[key] = m[key]
        for cat in CATEGORIES:
            row[f"precision_{cat}"] = m["per_category_precision"][cat]
            row[f"recall_{cat}"] = m["per_category_recall"][cat]
        baseline_rows.append(row)
    write_csv(pd.DataFrame(baseline_rows), out_dir / "baselines_report.csv")

    summary = _render_summary(metrics)
    (out_dir / "evaluation_summary.md").write_text(summary, encoding="utf-8")

    manifest = manifest_for_command(
        "p2_evaluate",
        config_hash=hash_files([str(policy_config), str(baseline_config)]),
        data_hash=hash_files([str(run_dir / "triage_results.csv")]),
        seed=seed,
        rule_version="1.2",
        results_hash=hash_files([str(out_dir / "evaluation_report.json")]),
        input_rows=len(results),
        excluded_rows=0,
        known_issues=[
            "Per-category precision is row-level; recall is perturbation-level.",
            "UNKNOWN and ambiguous/broken perturbations are measured as "
            "abstention behavior, not as category recall.",
        ],
    )
    write_json(manifest, out_dir / "manifest.json")
    pd.DataFrame(columns=["table", "file", "row_index", "column", "value", "reason"]).to_csv(
        out_dir / "excluded_rows.csv", index=False
    )

    receipt = {
        # The evaluated run is identified by its manifest run id (not its
        # filesystem path) so receipts reproduce byte-for-byte regardless of
        # where the run directory lives.
        "evaluated_run_id": (
            run_dir / "manifest.json").exists()
        and json.loads((run_dir / "manifest.json").read_text()).get("run_id")
        or run_dir.name,
        "anomaly_rows": len(results),
        "methods_compared": ["TRACE_LAB_MAIN"] + list(BASELINE_IDS),
        "main_method": {
            k: metrics["TRACE_LAB_MAIN"][k]
            for k in (
                "abstain_rate",
                "false_positive_rate_on_controls",
                "misattribution_rows",
                "detected_perturbations",
                "evaluable_perturbations",
            )
        },
    }
    write_json(receipt, out_dir / "run_receipt.json")

    log.info(f"evaluated {len(results)} anomaly rows against {len(perturbations)} perturbations and {len(controls)} controls")
    log.info(f"main abstain_rate={metrics['TRACE_LAB_MAIN']['abstain_rate']}")
    log.close()

    return {"metrics": metrics, "manifest": manifest, "out_dir": str(out_dir)}


def _locate_input(run_dir: Path, input_map: dict[str, str], fname: str) -> Path:
    """Find an input file by hash from the run's input hash manifest."""
    import json

    from ..common.hashing import hash_file

    # Preferred: the input directory recorded in the triage run receipt.
    candidates: list[Path] = []
    receipt_path = run_dir / "run_receipt.json"
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text())
            recorded = receipt.get("input_dir")
            if recorded:
                candidates.append(Path(recorded) / fname)
        except (ValueError, OSError):
            pass
    # Fallbacks: sibling synthetic_data directories (historical layout).
    candidates += [
        run_dir.parent.parent.parent / "synthetic_data" / fname,
        run_dir.parent.parent / "synthetic_data" / fname,
    ]
    expected = input_map.get(fname)
    for cand in candidates:
        if cand.exists() and (expected is None or hash_file(cand) == expected):
            return cand
    for cand in candidates:
        if cand.exists():
            return cand
    raise FileNotFoundError(f"cannot locate input file for evaluation: {fname}")


def _render_summary(metrics: dict[str, Any]) -> str:
    lines = ["# TRACE-LAB held-out perturbation evaluation", ""]
    main = metrics["TRACE_LAB_MAIN"]
    lines += [
        f"- anomaly rows: {main['total_anomaly_rows']}",
        f"- triage rows: {main['triage_rows']}; abstain rows: {main['abstain_rows']} "
        f"(abstain rate {main['abstain_rate']})",
        f"- evaluable perturbations: {main['evaluable_perturbations']}",
        f"- detected perturbations: {main['detected_perturbations']}",
        f"- misattribution rows: {main['misattribution_rows']}",
        f"- negative controls: {main['negative_controls']}; "
        f"false-positive rows on controls: {main['false_positive_rows_on_controls']} "
        f"(rate {main['false_positive_rate_on_controls']})",
        f"- ambiguous perturbations: {main['ambiguous_perturbations']} "
        f"(correctly abstained {main['ambiguous_correctly_abstained']})",
        f"- lineage-broken perturbations: {main['lineage_broken_perturbations']} "
        f"(correctly abstained {main['lineage_broken_correctly_abstained']})",
        f"- UNKNOWN perturbations: {main['unknown_perturbations']} "
        f"(correctly abstained {main['unknown_correctly_abstained']}, "
        f"mis-triaged {main['unknown_mis_triaged']})",
        "",
        "Per-category precision / recall (TRACE-LAB main):",
    ]
    for cat in CATEGORIES:
        lines.append(
            f"- {cat}: precision {main['per_category_precision'][cat]}, "
            f"recall {main['per_category_recall'][cat]}"
        )
    lines += ["", "Comparison across methods:", ""]
    lines.append("| method | abstain_rate | FP rate on controls | misattribution |")
    lines.append("|---|---|---|---|")
    for method, m in metrics.items():
        lines.append(
            f"| {method} | {m['abstain_rate']} | {m['false_positive_rate_on_controls']} "
            f"| {m['misattribution_rows']} |"
        )
    lines += [
        "",
        "TRIAGE rows are advisory human-review recommendations, not confirmed "
        "causal attributions.",
        "",
    ]
    return "\n".join(lines) + "\n"
