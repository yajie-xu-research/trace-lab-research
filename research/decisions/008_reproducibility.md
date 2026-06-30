# Decision 008 — Deterministic reproducibility: logical timestamps, frozen
# run ids, canonical hashing, and the re-computation test

**Status:** accepted · **Date:** 2026-06-30

## Context

A historical research repository must be re-runnable and auditable: the
same inputs must produce the same artifacts, and any later tampering with a
run must be detectable.

## Decision

- Generator seed fixed (20250110); two generations must be byte-identical.
- Manifest hashes (`config_hash`, `data_hash`, `results_hash`) computed
  with SHA-256 over canonicalized content (sorted keys, raw bytes in
  order); `result_hash` chains the stable fields and excludes execution
  context (operator, wall clock, environment).
- Historical run artifacts use deterministic run ids and timestamps;
  wall-clock values never enter run artifacts.
- Run status is one of `INTERNAL_RESEARCH` / `EXTERNAL_VALIDATION`;
  historical runs carry the former.
- A re-computation test runs validation, triage, and evaluation twice and
  compares every artifact byte-for-byte.

## Consequences

- `venv/bin/trace-lab` commands reproduce shipped artifacts exactly.
- A modified artifact changes `result_hash` and the manifest check fails
  (`trace-lab manifest inspect`).
