# Early-break warning (not an entry)

`QSMC_EarlyBreakDetector.mqh` is called once per newly closed chart bar by the
root and contributes a warning-only annotation to the market-direction label.
It never submits a candidate to the arbiter and cannot authorize an executable
entry.

## Inputs and causal handling

The detector consumes a closed OHLCV bar, previous close, ATR, current spread,
point size, and latest confirmed swing levels. It updates an EW mean/variance of
close-to-close returns normalized by ATR, then evaluates the current observation
against the **prior** EW baseline before incorporating that observation. A
standardized CUSUM uses `k=0.50`, `h=3.50`, sigma floor `0.05`; after a new alarm
it resets sums and applies a three-bar cooldown. The EW baseline continues during
the cooldown. Invalid measurements are rejected; `Reset` clears EW moments,
CUSUM, cooldown, timestamp and result. Duplicate/older bar timestamps are no-ops.

On root startup/rebuild, retained closed bars warm the EW/CUSUM state in
chronological order. The latest closed ATR (known at that decision boundary) is
used as the common scale for this warm-up; warnings from historical warm-up bars
are not published. Incremental bars use their own as-of ATR. Structure and early
break processing consume no forming-bar OHLC values.

## Features and score

Features are CUSUM alarm/side, z-score, body displacement in ATR, tick-volume
ratio against up to 20 preceding bars, candle close-location proxy, proximity to
the latest confirmed high/low, and spread/ATR penalty. Components have bounded,
documented weights in code and combine to a normalized 0–100 **heuristic score**.
A warning requires score at least 55 and either a fresh CUSUM alarm or at least
0.50 ATR body displacement. Missing tick volume/history/structure is represented
in `missing_mask`; scores are not probabilities and are not calibrated breakout
odds.

No historical aggressor-side bid/ask or order-book feed exists in this provider.
The implementation explicitly marks quote/order-book flow as missing. Candle
close location and broker tick volume are proxies, not true order flow or
centralized exchange volume. Excess spread reduces the score. A warning may be
shown alongside a neutral or mixed market direction; it must not be read as
confirmation or an entry signal.

## Complexity and checks

Each update is O(20) for the bounded tick-volume comparison, plus constant-time
EW/CUSUM and score arithmetic. The root updates only on new closed bars. The
MQL self-test checks flat data does not warn and missing quote-flow is reported;
`tools/test_early_break.py` checks directional symmetry, bounds, spread penalty,
and warning-only semantics. Neither substitutes for MetaEditor compilation or
historical out-of-sample calibration.
