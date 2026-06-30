# Decision 007 — Injected shifts: one 24-day perturbation per change, same-type
# per chain, spacing >= 35 days on multi-shift chains

**Status:** accepted · **Date:** 2026-06-25

## Context

Several dataset layouts were tried. Failures observed:

1. **Four short non-overlapping events per change** (the original model)
   produced cumulative schedule drift and window overlaps between events of
   different changes; attribution became lottery-like.
2. **Cross-type adjacency on one node** (semantic shift immediately
   followed by business shift on the same chain) made one detection window
   span both shifts; the stronger signature category won and the other
   event became a misattribution.
3. **Near-zero gap between consecutive shifts** (change spacing ~25 days
   with 24-day shifts) made the second shift invisible: its start boundary
   was polluted by the previous shift's tail and its end touched the next
   shift, so no window straddled a clean boundary.

## Decision

- One change injects exactly **one 24-day perturbation** and spreads its
  tickets across that window (4 spread tickets, occasionally 2 or 6).
- Each chain carries a single event kind: the N019 result chain is
  semantic-only; business shifts live on N017.
- Multi-shift chains space their changes **>= 35 days** apart, keeping a
  clean baseline gap between consecutive 24-day windows.
- Deliberate exception: the four ambiguous pairs and the broken-chain
  injections exist *by design* to exercise the abstention paths.

## Consequences

- Every detection window maps to at most one event kind on that node.
- Boundaries are clean; the change-point rule fires on both edges of every
  injected shift.
- The deliberate near-coincidences are the only ambiguity sources, which
  is what the counter-example table requires.
