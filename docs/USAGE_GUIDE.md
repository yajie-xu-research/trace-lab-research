# USAGE GUIDE — trace-lab-research

## Environment

Python 3.12; dependencies: numpy, pandas, pytest, pyyaml. Network access is
needed only for the initial install.

```
cd trace-lab-research
uv venv venv --python 3.12
uv pip install --python venv/bin/python3 -e .
```

All commands below assume the venv is active or the interpreter is called
explicitly (`venv/bin/trace-lab ...` / `venv/bin/python3 -m pytest tests/`).

## The five commands

| Command | Purpose |
| --- | --- |
| `trace-lab generate-synthetic` | generate the five tables + ground truth |
| `trace-lab validate` | schema-check the dataset |
| `trace-lab p2 triage` | anomaly detection → triage decisions |
| `trace-lab p2 evaluate` | held-out perturbation evaluation (incl. baselines) |
| `trace-lab manifest inspect` | verify a run manifest |

## 1. Generate synthetic data

```
trace-lab generate-synthetic --output synthetic_data/ --seed 20250110
```

Produces: the five tables, `defect_tickets.csv`, `perturbation_library.json`,
`normal_control_index.csv`. The generator is deterministic: same seed, same
bytes. Re-running overwrites the directory contents.

## 2. Validate

```
trace-lab validate --input synthetic_data/ --out outputs/runs/p2_validate/
```

Checks every table against `schemas/p2_tables.yaml`: format patterns,
enums, duplicate keys, timestamp ordering, required columns, cross-table
referential checks. Invalid rows are written to `excluded_rows.csv` with a
reason; the command exits non-zero when errors are present.

## 3. Triage

```
trace-lab p2 triage --input synthetic_data/ --out outputs/runs/p2_triage/
```

Reads **only** the five tables. Outputs:

- `triage_results.csv` — one row per anomaly: decision, reason code,
  candidate change ids, candidate categories, scores, lineage path,
  breakpoints, evidence JSON.
- `anomalies.csv` — the anomaly rows with raw observation indices.
- `excluded_rows.csv` — orphan observation rows (node not in lineage).
- `data/_ground_truth/true_defect_labels.csv` — evaluation-only copy. The
  copy step is skipped when ground-truth inputs are absent, and the triage
  outputs are byte-identical either way (see leakage test).

## 4. Evaluate (held-out)

```
trace-lab p2 evaluate --run outputs/runs/p2_triage/ --out outputs/runs/p2_evaluation/
```

Reads the triage run plus the ground truth the triage never saw. Produces:

- `evaluation_report.json` — per-method metrics (TRACE-LAB and B0–B3).
- `baselines_report.csv` — baseline decisions for inspection.
- `evaluation_summary.md` — human-readable summary.

## 5. Inspect a manifest

```
trace-lab manifest inspect --run outputs/runs/p2_triage/
```

Prints the manifest and verifies that `result_hash` recomputes from the
stable fields.

## Reproduce everything

```
rm -rf synthetic_data outputs/runs
trace-lab generate-synthetic --output synthetic_data/ --seed 20250110
trace-lab validate --input synthetic_data/ --out outputs/runs/p2_validate/
trace-lab p2 triage --input synthetic_data/ --out outputs/runs/p2_triage/
trace-lab p2 evaluate --run outputs/runs/p2_triage/ --out outputs/runs/p2_evaluation/
```

Because generation, scoring, and run ids are all deterministic, this
sequence reproduces the artifacts byte-for-byte
(verified by `tests/test_leakage_and_repro.py`).

## Tests

```
venv/bin/python3 -m pytest tests/
```

The suite covers the counter-example table (lineage-break abstention,
ambiguous near-coincident changes, normal-change negative controls, unknown
abstention), five-table validation, category dictionary precedence and
exclusivity, perturbation injection, leakage isolation, and full
re-computation reproducibility.

## Changing the method

- Scoring weights, windows, and thresholds live in
  `configs/p2_lineage.yaml` (policy rule version).
- Category signatures and precedence live in
  `configs/p2_categories.yaml`; it is frozen (2025-01-28) — changing it
  after an evaluation invalidates the comparison and must be recorded
  in `CHANGELOG.md` and a new research decision.
- Table contracts live in `schemas/p2_tables.yaml`.
- Baseline B3's site mapping lives in `configs/p2_baselines.yaml`.

## Known issue list

Recorded in every triage manifest `known_issues`:

1. Anomaly windows are fixed-width and overlapping; one underlying change
   can produce more than one anomaly row.
2. `TRIAGE` is advisory; it does not confirm causality.
