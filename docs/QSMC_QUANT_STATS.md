# Quantitative statistics primitives

`QSMC_Stats.mqh` contains optional, deterministic arithmetic primitives. They do
not generate entry signals and do not imply that a strategy has an edge. Callers
should only build a profile over a bounded, relevant range; do not run an
all-history profile on every tick.

## Exponentially weighted statistics (`CEWStatistics`)

`Update(state, x, alpha)` accepts finite `x` and `0 < alpha <= 1`. The first
sample initializes the state. Thereafter:

```
delta = x - mean
mean' = mean + alpha * delta
variance' = (1-alpha) * (variance + alpha * delta^2)
```

This is the weighted **population** variance under the same exponential
recurrence, not an unbiased sample-variance estimator. For `alpha=1`, the
latest observation replaces the prior distribution and variance becomes zero.
Invalid values are rejected without mutating the state. `Reset` returns to the
uninitialized state. `count` is a diagnostic update count; callers should reset
long-lived streams at their natural lifecycle boundary.

## Two-sided CUSUM (`CCUSUM`)

Each valid update standardizes against caller-supplied reference and scale:
`z=(x-reference)/sigma`, then updates `S+ = max(0,S+ + z-k)` and
`S- = max(0,S- - z-k)`. An alarm occurs when either sum reaches `h`; `k >= 0`
and `h > 0` are expressed in standardized units. The alarm and its side latch
until `Reset`; sums continue updating after an alarm. Invalid/nonpositive scale
or invalid thresholds return false without advancing state. This is a change
warning, not a breakout prediction or trade trigger. The caller owns reference,
scale, parameter selection, and reset boundaries.

## Wilson interval (`QSMC_WilsonInterval`)

Returns the two-sided Wilson score interval for `successes/trials` at the
provided positive normal quantile `z` (use 1.96 for the conventional approximate
95% interval). Requires `trials > 0` and `0 <= successes <= trials`. This interval
measures sampling uncertainty in an observed **binomial success rate only**.
It does not measure return magnitude, execution costs, drawdown, or
profitability. Outcomes must have a predeclared binary definition and independent
sampling assumptions must be considered by the caller.

## Volume profile (`CVolumeProfile`)

`Build(rates, start, count, bin_size, value_fraction, session_profile)` consumes
only the requested slice and uses `MqlRates.tick_volume`. It does not claim to
represent centralized exchange volume. Each bar's tick volume is distributed
equally across each price bin intersecting its `[low, high]` range. This is a
transparent OHLC allocation approximation, not true trade-at-price volume. A
zero-range bar is allocated to its one containing bin. Bin lower edges are
anchored at `floor(min_low / bin_size) * bin_size`; POC is the center of the
highest-volume bin (ties resolve to the lower-price bin). Value area expands
outward from POC by selecting the higher-volume adjacent bin until its volume
reaches `value_fraction * total`; equal adjacent volumes expand downward first.
`VAL` is the lower edge of the first included bin and `VAH` is the upper edge of
the last included bin.

Profiles are capped at 2,048 bins. Invalid ranges/parameters, no usable bars,
allocation failure, excessive range, or no positive tick volume return false and
leave `Result().valid == false` with a reason. `coverage` is valid bars with
positive tick volume / requested bars; invalid-price and zero/negative-volume
bars are excluded from both the price range and coverage. `total_tick_volume`
sums accepted broker tick volume. The result
also records time bounds and whether the caller declared it a session profile;
that flag does not infer exchange sessions. Build only on an appropriate session
or rolling window and refresh at a suitable cadence. Work is proportional to the
number of bar/bin intersections and is bounded by the bin cap.

## Tests and integration boundary

`tools/test_quant_stats.py` is an independent arithmetic reference, run in CI.
`CArbSelfTest::T11_QuantitativePrimitives` exercises the MQL implementation when
`QSMC_ArbiterTest.mq5` runs in MetaTrader. The offline suite is not a substitute
for compiling with MetaEditor. These primitives are currently not wired into the
signal path, persistence, or scanner; that avoids implying they affect published
signals before their input ranges and lifecycle are deliberately integrated.
