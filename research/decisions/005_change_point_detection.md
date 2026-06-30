# Decision 005 — Change-point detection: per-window std with a noise cap and effect-size floor

**Status:** accepted · **Date:** 2026-06-20

## Context

Three failure modes were observed while tuning the change-point rule on the
generated stream:

1. **Node-wide baseline std hides shifts.** Estimating the window variance
   from the node's full history inflated the noise term (the shift itself
   is part of that history), so real shifts no longer exceeded the z
   threshold.
2. **Mixed halves hide shifts.** When a detection window straddles a shift
   boundary, the half containing both shifted and unshifted rows has large
   variance dominated by the shift — the very signal being tested — and the
   mean jump is diluted below the effect floor.
3. **Tiny-window false positives.** A small random window with an
   accidentally tiny estimated std turns a meaningless 0.4-unit wobble into
   a huge z.

## Decision

- Use the per-window first-half standard deviation.
- Cap the effective noise at 0.35: boundary windows whose half straddles a
  shift still fire.
- Require `|diff| >= 0.75` (effect-size floor) so a small wobble never
  fires regardless of z.

Both constants are policy-level design parameters, not fitted to
ground-truth labels.

## Consequences

- Back-to-back shifts with a clean baseline gap are detected at both
  boundaries.
- Random false positives on numeric fields are negligible (the floor
  dominates).
- Adjacent same-node shifts with near-zero gaps remain invisible by
  construction; the data design spaces events >= 35 days apart
  (Decision 007).
