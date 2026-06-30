# External Validation Protocol — Draft

**Status:** DRAFT · **Execution:** NOT_OBTAINED · **Last revised:** 2026-06-30

## Purpose

TRACE-LAB has been exercised on generated data with an internal held-out
evaluation (see `docs/frozen_metrics.md`). This protocol defines how an
independent party would validate the method on a different, externally
supplied data model and dataset, without access to this repository's
internal ground-truth machinery.

Nothing in this file claims such validation has happened. The status file
(`status.json`) records `NOT_OBTAINED`.

## Scope

1. **Cross-model transfer.** The external party supplies its own schema,
   lineage table, and change register (a second data model with different
   field names, node naming, and change categories). The repository's
   `second_schema/` directory documents an internal rehearsal of this step
   and must not be shared with the external party before its protocol run.

2. **Blind perturbation.** The external party injects its own controlled
   changes and defects, records the ground truth separately, and runs the
   five-command pipeline:

   ```
   trace-lab generate-synthetic   (not used externally; external party
                                   supplies real or third-party data)
   trace-lab validate
   trace-lab p2 triage
   trace-lab p2 evaluate
   trace-lab manifest inspect
   ```

3. **Metric contract.** The external party reports, per category:
   precision, recall, abstention rate, false-positive rate on negative
   controls, and misattribution rows, using the same metric definitions as
   `docs/METHOD_CARD.md` section 11.

4. **Isolation re-verification.** The external party re-runs triage after
   deleting its ground-truth files and confirms byte-identical triage
   outputs (leakage check).

## Deliverables the external party returns

- `results_return_template.csv` filled with the metric rows;
- its protocol deviations, if any, recorded in writing;
- a statement of whether its data was real or independently generated.

## Acceptance

| Criterion | Threshold |
| --- | --- |
| Leakage check | byte-identical triage outputs without ground truth |
| Per-category precision | reported without modification |
| Per-category recall | reported without modification |
| False-positive rate on controls | reported without modification |
| Abstention reason codes | restricted to the three frozen codes |

The thresholds are deliberately left open: the purpose of external
validation is an independent measurement, not a pass mark defined by the
authors.

## Prohibitions for the external party

- No access to this repository's `outputs/` or ground-truth inputs before
  its own run.
- No modification of `configs/p2_categories.yaml` (frozen) or
  `configs/p2_lineage.yaml` (policy 1.2) without recording it as a
  protocol deviation.

## Status

`NOT_OBTAINED` — see `status.json`.
