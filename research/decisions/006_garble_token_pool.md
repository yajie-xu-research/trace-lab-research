# Decision 006 — Garble tokens must genuinely fail the field format pattern

**Status:** accepted · **Date:** 2026-06-20

## Context

The interface-mapping garble perturbation writes malformed raw values. Two
token choices ("0x7F", then "..") silently passed the string format pattern
(`^[A-Za-z0-9_. \-]{1,64}$` — dots and hex letters are allowed), so the
FORMAT_VIOLATION rule never fired and injected events went undetected.

## Decision

The garble token pool is restricted to tokens that contain characters
outside every format pattern's allowed set:

- `??` (question mark)
- `1,23` (comma)
- `#!` (hash + bang)
- `#ERR` (hash)

A comment next to the pool documents the invariant, and a test
(`test_garble_tokens_fail_format_pattern`) asserts every garble token in
the generated stream fails the string pattern.

## Consequences

- Format-violation injections are actually visible to the detector.
- The invariant is regression-tested, so a future token addition that
  passes the pattern fails CI instead of silently degrading recall.
