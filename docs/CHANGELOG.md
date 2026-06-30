# CHANGELOG — trace-lab-research

## 1.2.0 — 2026-06-30

### Method

- Candidate window anchored to the anomaly window start; lookback 25 days,
  lookahead 21 days (policy 1.2).
- Symptom-type match now uses the frozen signature weight directly as the
  score term (previously a binary match under a fixed weight).
- Continuous time-proximity bonus `max(0, 1 − days_before/25)` replaces the
  window-span bonus.
- `NORMAL_CHANGE` negative controls contribute zero symptom evidence; they
  resolve to the non-defect verdict `TRUE_BUSINESS_CHANGE` and can no
  longer tie or steal real business changes.
- Ambiguity rule: near-coincident candidates (overlapping effective
  windows, scores within 0.5, dates within 7 days) abstain with
  `AMBIGUOUS_CANDIDATES`.
- `EXTRACTION_FAILURE` signature reduced to `MISSING_RATE_SHIFT` (removed
  `FORMAT_VIOLATION`) to stop noise garbles from being attributed to
  extraction changes.

### Detection

- Change-point detector: per-window standard deviation with an effective
  noise cap (0.35) so shift-boundary windows still fire, and an
  effect-size floor (0.75) against small-variance false positives.
- Garble token pool restricted to tokens that genuinely fail the field
  format patterns (e.g. `#!`, `#ERR`, `??`, `1,23`).

### Data

- Business shifts moved off the N019 chain to N017 (spacing >= 35 days)
  so consecutive 24-day shifts keep a clean baseline gap; semantic shifts
  stay on N019. This removes cross-type adjacency that competed inside one
  detection window.

### Baselines and cross-model transfer rehearsal

- Baselines B0–B3 with a static site mapping table (frozen for the studied
  site, abstains on unknown combinations).
- `second_schema/` cross-model transfer rehearsal introduced (internal).

### Tooling

- `trace-lab` CLI with five commands; manifests, receipts, and logs for
  every run; excluded-row accounting everywhere.
- Fixed: input-hash write crashed when the ground-truth copy was skipped
  (the leakage path); the `data/` directory is now created unconditionally.
- Fixed: triage row construction from anomaly dicts; anomaly/result
  DataFrames.
- Removed operator default that referenced a person name
  (`trace-lab-maintainer` now).

### Evaluation

- Per-category precision/recall computed at perturbation level (fixes the
  double-counting that allowed recall > 1).
- Ground-truth isolation: triage reads only the five tables; leakage test
  proves byte-identical outputs without ground truth.
- 39/39 evaluable perturbations detected; misattribution 0; FPR on
  negative controls 0.0 (see `docs/frozen_metrics.md`).

## 1.0.0 — 2026-01-15

- Five-table dataset contract, versioned lineage graph with
  `valid_from`/`valid_to`, six-category frozen dictionary (2025-01-28),
  five anomaly rules, transparent scoring with two required gates, triage
  decision codes, deterministic generator (seed 20250110), deterministic
  run ids, result hashing.

## 0.7.0 — 2025-09-18

- Held-out perturbation evaluation: controlled perturbation library, negative
  controls for true business change, transparent rule scoring with two
  required gates, abstention and ambiguity rules, and the evaluation
  harness.

## 0.3.0 — 2025-04-15

- Initial pipeline: category dictionary v1.0 (frozen 2025-01-28), field
  lineage graph prototype, anomaly rule sketch, lineage-aware candidate
  search, and the seeded synthetic defect dataset (seed 20250110).
