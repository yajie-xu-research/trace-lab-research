# METHOD CARD — TRACE-LAB (P2 scope)

**Method id:** `P2_TRACE_LAB` · **Rule version:** 1.2 (2026-06-12) ·
**Category dictionary:** frozen rule_version 1.0 (2025-01-28) ·
**Status:** internal research (external validation pending)

## 1. What the method does

TRACE-LAB answers one question per detected anomaly:

> Which upstream change in the versioned lineage can best explain this
> field-level anomaly — and what defect category does that change point to?

It never asserts causation. Its output is a decision per anomaly window:

- `TRIAGE` — one or more candidate changes with transparent scores, to be
  human-reviewed; or
- `ABSTAIN` — with a reason code (`AMBIGUOUS_CANDIDATES`,
  `LINEAGE_UNRESOLVED`, `INSUFFICIENT_EVIDENCE`).

## 2. Pipeline

```
five-table dataset ──validate──▶ anomaly detection ──▶ lineage resolution
     (seed 20250110)   (schema)    (5 rules, fixed      (versioned graph,
                                   windows)             valid_from/valid_to)
                                                              │
   candidate search ◀── change register ──────────────────────┘
        │                    (versioned, ticket_index dropped)
        ▼
   transparent scoring (two required gates + evidence terms)
        ▼
   precedence & ambiguity resolution (frozen dictionary)
        ▼
   TRIAGE / ABSTAIN ──▶ held-out evaluation (ground truth isolated)
```

## 3. Inputs

1. `lineage_nodes` — versioned node table (SCHEMA_V1 valid through
   2025-06-01; 24 of 32 nodes close at the boundary and eight long-lived
   fields stay open-ended, SCHEMA_V2 from 2025-06-01).
2. `lineage_edges` — versioned transform edges.
3. `schema_changes` — change register with `effective_at`, `affected_nodes`,
   `change_category`; its `ticket_index` column is dropped before scoring so
   triage cannot see whether a change already has a ticket.
4. `field_profiles` — datatype, allowed range, unit, missing-rate profile.
5. `field_observations` — the observed stream.

## 4. Anomaly detection

Five rules over fixed-width overlapping windows (window size and step are
policy constants):

| Rule | Signal |
| --- | --- |
| `FORMAT_VIOLATION` | raw value fails the field's format pattern |
| `RANGE_VIOLATION` | parsed value outside the allowed range |
| `UNIT_DEVIATION` | recorded unit differs from the profile unit |
| `MISSING_RATE_SHIFT` | missing fraction jumps above the profile threshold |
| `CHANGE_POINT` | first/second-half mean shift with z and effect-size floors |

Every anomaly row carries: `anomaly_id`, `node_id`, `rule`, `window_start`,
`window_end`, `raw_indices` (row indices into the observation stream),
`n_observations`, and rule-specific `details`.

## 5. Lineage resolution

The versioned graph resolves the upstream path of the anomaly node at the
anomaly time. Failures are explicit:

- **break** — a node expects upstream input but no incoming edge is valid;
- **cycle** — the walk revisits a node;
- **contradiction** — overlapping edges with different transforms/rules.

A true source node (no edge ever targets it) is a valid chain end; an
expired edge on a non-source is a break.

## 6. Candidate construction

Candidates are changes in the register that (a) affect a node on the
resolved path and (b) took effect within `[window_start − lookback,
window_start + lookahead]` (policy: lookback 25, lookahead 21 days). The
candidate carries `node_distance` (hops from the anomaly node) and whether
the change covers the anomaly node directly.

## 7. Transparent scoring

Two **required gates** — failing either zeroes the candidate:

1. `lineage_path_association` — the change affects a node on the resolved
   path;
2. `time_validity` — the change took effect inside the candidate window.

Evidence terms (recorded per candidate):

| Term | Weight |
| --- | --- |
| symptom-type match (frozen signature weight 0..3) | up to 3.0 |
| time proximity `max(0, 1 − days_before/25)` | 1.0 |
| missing-pattern alignment | 1.0 |
| node-distance penalty per hop | −0.2 |
| change covers the anomaly node | +1.0 |
| counter-example found | −3.0 |

`NORMAL_CHANGE` records are negative controls: they map to the non-defect
verdict `TRUE_BUSINESS_CHANGE` and contribute **zero** symptom evidence.
They can never explain an anomaly on their own.

## 8. Precedence and ambiguity

Frozen precedence (`UNIT_CHANGE` precedes `INTERFACE_MAPPING_ERROR`;
`EXTRACTION_FAILURE` precedes `INTERFACE_MAPPING_ERROR`) applies between
candidates: the higher category wins only if its score is strictly higher.
If two candidates with overlapping effective windows land within
`tie_epsilon` (0.5) and their change dates are within `ambiguous_window_days`
(7), the anomaly is `ABSTAIN` / `AMBIGUOUS_CANDIDATES`.

## 9. Decision rules

| Condition | Decision |
| --- | --- |
| A candidate passes both gates with score ≥ `min_triage_score` (4.0) | `TRIAGE` |
| Lineage broken/cyclic/contradictory | `ABSTAIN` / `LINEAGE_UNRESOLVED` |
| ≥2 near-coincident candidates within tie epsilon | `ABSTAIN` / `AMBIGUOUS_CANDIDATES` |
| Otherwise | `ABSTAIN` / `INSUFFICIENT_EVIDENCE` |

## 10. Baselines

- **B0_SINGLE_FIELD_RULES** — anomaly rule mapped to a category by a fixed
  rule-to-category table; no lineage.
- **B1_NO_LINEAGE_DETECTION** — same detector, but candidates are the
  temporally nearest changes regardless of lineage.
- **B2_CHANGE_POINT_ONLY** — ordinary change-point detection; attributes to
  the most recent change regardless of type or lineage.
- **B3_SITE_MAPPING_TABLE** — a static site-specific `(system, anomaly_rule)
  → category` table; unknown combinations abstain.

## 11. Held-out evaluation

The evaluation harness reads the perturbation plan and ticket ground truth
that triage never sees. Metrics: per-category precision/recall, abstention
rate, false-positive rate on normal-change negative controls, ambiguity and
lineage-break abstention accounting, and misattribution rows. See
`docs/frozen_metrics.md` for the locked results.

## 12. Isolation and reproducibility

- Ground truth lives only under `run/data/_ground_truth/`; the leakage test
  proves triage outputs are byte-identical without it.
- Run ids and timestamps are deterministic; re-running the documented
  commands reproduces the committed artifacts byte-for-byte.
- `result_hash` chains `config_hash`, `data_hash`, `results_hash`, seed, and
  rule version into a single deterministic manifest digest.

## 13. Known limits

- Windows are fixed-width and overlapping; one change can produce several
  anomaly rows (recorded in every triage manifest).
- The method's behavior is shown on generated data; transfer to a second
  schema is probed internally in `second_schema/` and externally pending.
- `TRIAGE` is advisory, never a confirmation of causation.
