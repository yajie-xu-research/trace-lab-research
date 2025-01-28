# Decision 001 — Six frozen defect categories with precedence and exclusivity

**Status:** accepted · **Date:** 2025-01-28 (dictionary frozen) · **Rule version:** 1.0

## Context

Anomaly symptoms are ambiguous: a range violation can indicate a unit change,
a mapping error, or a real business change. Triage needs a fixed vocabulary
with rules that resolve symptom overlap deterministically.

## Decision

Six categories, mutually exclusive per confirmed root cause:

1. UNIT_CHANGE
2. INTERFACE_MAPPING_ERROR
3. FIELD_SEMANTIC_CHANGE
4. EXTRACTION_FAILURE
5. TRUE_BUSINESS_CHANGE (a real change, not a defect)
6. UNKNOWN (abstain fallback)

Each category declares `symptom_signatures` (anomaly rules with weights
0..3), `matching_change_categories`, `precedence_over`, and
`exclusive_with`.

- `UNIT_CHANGE` precedes `INTERFACE_MAPPING_ERROR` (a wrong-unit field is
  more specific than a wrong mapping).
- `EXTRACTION_FAILURE` precedes `INTERFACE_MAPPING_ERROR`.
- `TRUE_BUSINESS_CHANGE` excludes every defect category; `UNKNOWN` excludes
  everything.

Precedence is applied **between candidates, never between tickets**: a
higher-precedence category wins only when its symptom score strictly beats
the other; otherwise the anomaly stays ambiguous.

## Consequences

- Scoring and abstention are deterministic and auditable.
- The dictionary is frozen before any evaluation; post-freeze changes
  invalidate the comparison and require a new rule version.
