# Decision 004 — Normal-change negative controls carry zero explanatory weight

**Status:** accepted · **Date:** 2026-06-12

## Context

The change register includes routine maintenance changes that never change
data behavior (negative controls). Mapping them to a defect category would
create false alarms; leaving them uncategorizable created a different
problem: they tied against real business changes inside the same window and
forced spurious abstentions.

## Decision

- `NORMAL_CHANGE` resolves to the non-defect verdict
  `TRUE_BUSINESS_CHANGE` in the category mapping (a routine change *is* a
  business change, not a defect).
- In scoring, a `NORMAL_CHANGE` candidate contributes **zero** symptom
  evidence, so it can never win a tie against a real change and never
  explains an anomaly on its own. The zero weight is recorded in the
  candidate evidence as `normal_change_control: true`.

## Consequences

- Negative controls are never reported as defects (counter-example table).
- Real business changes are not stolen by nearby routine changes.
- An anomaly near only a normal change abstains with
  `INSUFFICIENT_EVIDENCE` — the conservative, correct outcome.
