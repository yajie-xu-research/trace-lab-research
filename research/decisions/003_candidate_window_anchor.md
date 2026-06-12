# Decision 003 — Candidate window anchored at the anomaly window start

**Status:** accepted · **Date:** 2026-06-12 · **Policy rule version:** 1.2

## Context

Early runs anchored the candidate window at the anomaly row timestamp
(mid-window). A change-point window spans several weeks, and its *second
half* shift is caused by a change that took effect just before the window
*start*. Anchoring at the middle pushed that change outside lookback.

## Decision

The candidate window is `[window_start − lookback, window_start +
lookahead]` with lookback 25 days and lookahead 21 days. Lookahead is
sized to roughly one window width so a change effective inside the window
(which explains its second half) is found.

Causality ordering: a change must precede the anomaly, but a change that
takes effect inside the anomaly window itself can explain the later part
of that window — hence the tolerance is asymmetric and anchored to the
start.

## Consequences

- Change-point events whose effective date falls inside the anomaly window
  are candidates (required for recall).
- Changes taking effect after the window cannot explain it (excluded by
  the lookahead bound).
