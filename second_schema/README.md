# second_schema — internal cross-model rehearsal

**Status:** INTERNAL_ONLY (design verification) · **Date:** 2026-06-30

## Purpose

TRACE-LAB's real challenge is transfer: the anomaly rules, the lineage
resolution, and the candidate scoring are written against one data model.
This directory rehearses the cross-model step internally with a second,
deliberately different data model — different node naming, different
systems, different change vocabulary — and records where the method
transfers cleanly and where a port would need explicit adaptation.

This rehearsal is **not** external validation. `external/status.json`
records cross-model validation as `NOT_OBTAINED`; this directory is
excluded from the external protocol handoff.

## The second model (v2_schema)

| Aspect | Primary schema | Second schema |
| --- | --- | --- |
| Node naming | `N001`…`N032` | `nd_alpha`…`nd_mu` (greek-ish handles) |
| Edge transform ids | `T001`…`T040` | `tf.a01`…`tf.a24` |
| Schema versions | SCHEMA_V1 / SCHEMA_V2 | `ERA_2024` / `ERA_2025` |
| Systems | ANALYZER / ETL / LIS / INTERFACE / REPORT | COLLECTOR / NORMALIZER / STORE / FEED |
| Change categories | UNIT_REDEFINITION, INTERFACE_REMAP, … | `unit_conv`, `feed_map`, `calc_rule`, `job_change`, `policy` |
| Valid fields | valid_from / valid_to | `active_from` / `active_to` |

Files:

- `v2_nodes.csv` — node table in the second naming scheme.
- `v2_edges.csv` — transform edges.
- `v2_profiles.csv` — field profiles.
- `v2_changes.csv` — change register in the second vocabulary.

## Transfer analysis

| Component | Transfers? | Notes |
| --- | --- | --- |
| Anomaly rules (format/range/unit/missing/change-point) | yes | operate on (node, window, value); column names are the only coupling |
| Window mechanics | yes | policy constants are schema-agnostic |
| Lineage resolution | yes, with mapping | the graph walks `from → to` edges with validity ranges; a port must map `active_from/active_to` to `valid_from/valid_to` |
| Candidate search | yes, with mapping | `affected_nodes`, `effective_at`, window anchoring all schema-agnostic |
| Category dictionary | **no** | frozen to the primary change vocabulary; a port must write a new frozen dictionary for the second vocabulary *before* any evaluation |
| Baselines | partial | B0/B1/B2 transfer; B3's site mapping table is primary-schema-only by construction |
| Evaluation harness | yes | perturbation plan format is independent of node naming |

## Conclusion of the rehearsal

The method transfers except for two deliberate, documented seams:

1. **Column mapping** (validity fields, change fields) — a small adapter,
   not a method change.
2. **The frozen category dictionary** — must be re-authored per data
   model, before evaluation, under the same freeze discipline
   (research/decisions/001).

These seams are exactly what the external protocol will exercise for real.
