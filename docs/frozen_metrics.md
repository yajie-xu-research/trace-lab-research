# Frozen Metrics — TRACE-LAB held-out perturbation evaluation

**Frozen:** 2026-06-30 · **Policy rule version:** 1.2 ·
**Category dictionary:** 1.0 (frozen 2025-01-28) · **Seed:** 20250110 ·
**Run status:** INTERNAL_RESEARCH · **Scope:** generated data only

These metrics were produced by `p2 evaluate` against the triage run under
`outputs/runs/p2_triage/`. They are locked with the repository release; any
code change that alters them must land in a new CHANGELOG entry with new
metrics. The evaluator held ground truth that triage never reads.

## Run manifest (constituents)

Triage run (`outputs/runs/p2_triage/manifest.json`):

| Field | Value |
| --- | --- |
| run_id | `run-p2-trace-lab-p2-triage-20260628T090000Z` |
| utc | `2026-06-28T09:00:00Z` |
| seed | `20250110` |
| rule version | `1.2` |
| config_hash | `77dd20f98776473ef259f5dcac4d9a80f6e525afadb2828dd4fb4e06af97f44c` |
| data_hash | `f0dca3395c751a1462e952cb140dae3a271cced6166bc5a2fc3c844736da4762` |
| results_hash | `3422ce0450edd37ef605b9a1da3130e2c5d7d15c7a9f640bdcf0a986ba0c94e2` |
| result_hash | `e8de399cdf8119d120123ddcbb6fd5d8b1660fb0b5e1027fb524ac7aa1295a79` |

Evaluation run (`outputs/runs/p2_evaluation/manifest.json`):

| Field | Value |
| --- | --- |
| run_id | `run-p2-trace-lab-p2-evaluate-20260628T091500Z` |
| utc | `2026-06-28T09:15:00Z` |
| config_hash | `b89c9746462b99fb44c267abff0b49a1e406c2710ecf6f1d48c4782c88bcface` |
| data_hash | `cea164366c9889e1e11793444b7e89f44134bf58ae6b57d77ad8d9ae16e95b14` |
| results_hash | `401742caae12e81f5b39fea9d36506b9dd7be99d10ae99afac80aafdcab02ae6` |
| result_hash | `5611267208aeee7c1907ff6767be3194fe45023ffa9cc94161800e499e98d0a4` |

The triage data_hash covers the five triage-visible tables
(`lineage_nodes`, `lineage_edges`, `schema_changes`, `field_profiles`,
`field_observations`) plus the perturbation plan and control index;
ground-truth tickets are evaluation-side inputs and do not enter the triage
data hash. Generated on 2026-06-30 from code version `1.2.0` (see the run
manifests for the recorded commit).

## Dataset snapshot

| Item | Count |
| --- | --- |
| lineage nodes / edges | 32 / 40 |
| schema changes (defect + normal) | 117 (52 defect, 65 normal controls) |
| field observations | 2020 |
| defect tickets | 180 (INTERFACE 48, UNIT 40, EXTRACTION 30, SEMANTIC 26, BUSINESS 18, UNKNOWN 18) |
| perturbations | 66 (UNIT 10, INTERFACE 15, EXTRACTION 12, SEMANTIC 7, BUSINESS 4, UNKNOWN 18) |
| ambiguous pairs / lineage-broken injections | 4 / 5 |

Schema-version windows: 24 of the 32 `SCHEMA_V1` nodes close at the
2025-06-01 boundary (valid_to = boundary instant, exclusive); eight
long-lived V1 fields stay open-ended and keep observations after the
boundary. All `SCHEMA_V2` nodes open at the same boundary instant.

## Anomaly detection

- Anomaly rows detected: 210
- Triage rows: 102 · Abstain rows: 108 (abstention rate **0.5143**)
  (abstain reasons: INSUFFICIENT_EVIDENCE 95, AMBIGUOUS_CANDIDATES 11,
  LINEAGE_UNRESOLVED 2)

## TRACE-LAB main method

| Category | Precision | Recall |
| --- | --- | --- |
| UNIT_CHANGE | 1.0000 | 1.0000 |
| INTERFACE_MAPPING_ERROR | 0.9688 | 1.0000 |
| FIELD_SEMANTIC_CHANGE | 1.0000 | 1.0000 |
| EXTRACTION_FAILURE | 1.0000 | 1.0000 |
| TRUE_BUSINESS_CHANGE | 1.0000 | 1.0000 |
| UNKNOWN | n/a (abstention behavior) | n/a |

- Evaluable perturbations: 39 · Detected: 39 (all five defect/business kinds)
- Misattribution rows: **0**
- False-positive rows on 65 negative controls: **0** (rate 0.0)

Row-level precision note (INTERFACE_MAPPING_ERROR): precision 0.9688 is
31/32 at the row level. 32 TRIAGE rows carry an INTERFACE_MAPPING_ERROR
candidate; 31 match INTERFACE perturbations. The remaining row
(`ANOM000150`) matches perturbation `P0032`, which belongs to ambiguous
near-coincident pair `PAIR-1`; the evaluator excludes ambiguous-pair rows
from the true-positive numerator by design, so the row is neither counted
as a hit nor as a misattribution (perturbation-level misattribution is 0).

Negative-control note: false positives on controls count only
defect-category verdicts. Of the 65 NORMAL_CHANGE negative controls, 5
anomaly rows overlap control windows; all 5 abstained
(INSUFFICIENT_EVIDENCE), so zero control-overlapping rows carried a defect
verdict (rate 0.0 = 0/5).

## Abstention accounting (counter-example table)

| Scenario | Perturbations | Correctly abstained |
| --- | --- | --- |
| Ambiguous near-coincident changes | 4 | 8 anomaly rows |
| Lineage break (broken chain) | 5 | 2 rows (remaining rows outside lineage) |
| UNKNOWN (no change record) | 18 | 40 rows abstained, **0 mis-triaged** |

## Baseline comparison (same anomaly set, same ground truth)

| Method | Abstain rate | FP rate on controls | Misattribution rows |
| --- | --- | --- | --- |
| TRACE_LAB (main) | 0.514 | 0.000 | 0 |
| B0_SINGLE_FIELD_RULES | 0.000 | 1.000 | 46 |
| B1_NO_LINEAGE_DETECTION | 0.009 | 0.000 | 103 |
| B2_CHANGE_POINT_ONLY | 0.862 | 0.000 | 19 |
| B3_SITE_MAPPING_TABLE | 0.000 | 1.000 | 46 |

Reading: B0/B3 (static rule and mapping tables) report everything including
all controls, B1 attributes to the nearest change regardless of lineage and
misattributes 103 rows, B2 abstains most of the time. TRACE-LAB is the only
method with zero false positives on controls and zero misattribution, at a
deliberate cost: half of all anomaly rows abstain for human review instead
of being guessed.

## Verification of this document

```
venv/bin/trace-lab manifest inspect --run outputs/runs/p2_triage/
venv/bin/python3 -c "import json;print(json.load(open('outputs/runs/p2_evaluation/evaluation_report.json'))['TRACE_LAB_MAIN'])"
```

Re-running the documented five-command pipeline reproduces every artifact
byte-for-byte (see `tests/test_leakage_and_repro.py` and
`outputs/runs/reproducibility_check.log`).

## What these metrics do NOT claim

- They describe behavior on generated data with controlled injections, not
  on real records.
- `TRIAGE` rows are advisory human-review recommendations, not causal
  confirmations.
- External validation is NOT_OBTAINED (`external/status.json`).
