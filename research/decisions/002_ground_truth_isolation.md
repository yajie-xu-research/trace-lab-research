# Decision 002 — Ground truth is evaluation-only and never a triage feature

**Status:** accepted · **Date:** 2026-05-30

## Context

The perturbation plan and the defect tickets define what the method *should*
find. If triage could see them (directly or through a side channel), any
metric would be circular.

## Decision

- Triage reads exactly five files: `lineage_nodes`, `lineage_edges`,
  `schema_changes`, `field_profiles`, `field_observations`.
- The `ticket_index` column of the change register is dropped before
  candidate construction — triage cannot see whether a change already has
  a ticket.
- Triage stages the ground-truth labels only under
  `run/data/_ground_truth/` for the evaluator; it never reads that
  directory.
- A leakage test deletes the three ground-truth inputs and asserts triage
  outputs are byte-identical.

## Consequences

- The held-out evaluation is meaningful: the evaluator holds the ground
  truth, the method holds none of it.
- The `_ground_truth` directory is documented as evaluation-only.
