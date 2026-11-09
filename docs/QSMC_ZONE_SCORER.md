# ZoneScorer

`QSMC_ZoneScorer.mqh` applies mandatory zone validity checks before assigning a
soft context rank. It is called for the root's tactical zone-reaction candidates;
its score affects candidate ranking, not whether mandatory gates pass.

## Hard validity gates

Reject invalid/unstable-ID/malformed/neutral/expired zones, a closed break without
a confirmed flip and retest, a zone whose effective support/resistance role
conflicts with candidate direction, invalid price/ATR, a zone outside 2.5 ATR, or
structural strength below the configured minimum. A high soft score cannot bypass
these conditions. The existing location, reaction, stop, room, spread, data and
closed-bar gates remain in force.

## Soft score (0–100; not probability)

The independent context weights are HTF alignment 12, structural quality 25,
freshness 15, distance 20, opposing-zone room 15, and spread condition 13.
HTF opposition contributes -12; neutral/unknown HTF contributes zero and sets a
missing-data bit. Freshness uses the zone's closed-bar touch count (one or fewer
= 15; two = 11; three/four = 6; more = 0 with a penalty). Distance fades linearly
to zero at 2.5 ATR; room reaches full contribution at 2.5 ATR; spread fades to zero
at 0.15 ATR. Missing room/spread are marked and contribute zero. Penalties and
component values are returned as data, not hidden in a single number.

Reaction evidence is kept separate: candidate ranking combines a normalized
reaction evidence component (65%) with zone context (35%). The zone score does not
repeat wick/candle/volume/sweep/displacement evidence, avoiding those correlated
features being counted twice. The exact breakdown is attached to candidate
metadata/tooltips. This is a deterministic ranking heuristic, not a calibrated
probability or expected return.

## Tests

`CArbSelfTest::T14_ZoneScorer` covers role gates, invalidated zones, score bounds,
missing-data indicators, and monotonic distance/room/spread behavior.
`tools/test_zone_scoring.py` is an independent arithmetic contract suite.
