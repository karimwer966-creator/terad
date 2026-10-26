# Causal market-structure engine

`QSMC_Structure.mqh` provides `CStructureEngine`, included and consumed by the
QSMC root for a chart-corner market-direction context. It is not an entry engine
and does not independently authorize signals. The existing arbiter remains the
only publisher.

## Input and timing contract

`ProcessClosed(rates, closed_index, availability_time, atr, events)` requires
`rates` in chronological order (oldest first), and the index of a fully closed
bar. It validates the local OHLC window and strictly increasing timestamps.
The caller must process closed bars in order, beginning no earlier than
`left_bars + right_bars`, and provide the time at which the closed-bar facts
became available (normally the next bar open). Reprocessing the same or an older
bar is a successful no-op with an empty event list. Invalid inputs return false
without advancing state.

A swing at pivot index `p` is a **strict** maximum/minimum over `left_bars` bars
before and `right_bars` bars after it. Ties/plateaus are not swings. Because the
pivot is evaluated only while processing `p + right_bars`, it cannot be known
before those right bars have closed. Swing events have `event_time` at the pivot
bar and `available_time` at the caller-supplied confirmation boundary. Consumers
must use `available_time` to prevent historical look-ahead.

## Structure state and events

Confirmed highs are compared with the prior confirmed high: a move above the
configured absolute tolerance emits HH; a move below emits LH; a move within it
emits equal-high. Lows similarly produce HL, LL, or equal-low. BOS requires a
closed close beyond the latest confirmed opposite swing by `break_buffer`.
Wick penetration alone is not BOS. From neutral, the first directional break is
BOS and establishes direction. A break against the current direction is CHoCH;
it also emits structural invalidation and flips the directional state. A later
same-direction confirmed break is BOS. Repeated closes past the same reference
swing do not repeatedly emit the event.

Liquidity pools are deliberately narrower than a list of local pivots: only a
pair/cluster of confirmed equal highs/lows within `equal_tolerance` is labelled
buy-side/sell-side liquidity. One pivot is not a pool. A high-side sweep requires
wick penetration past the active equal-high level by `sweep_penetration` and a
close at/below the pool; a low-side sweep is symmetric. A close beyond the pool
by `break_buffer` is a separate breakout event. Each active pool is consumed by
its first sweep or breakout to suppress repeats.

Bullish/bearish displacement is a closed bar whose absolute body is at least
`displacement_atr * atr` and whose body/range meets `min_body_fraction`. Invalid
or nonpositive ATR suppresses displacement only. It does not suppress structure
processing. Parameters are absolute price distances except ATR-normalized
`displacement_atr`.

Event IDs include symbol, timeframe, event type, event time, and reference time.
The engine emits at most 16 events per processed bar. Invalid config is rejected
by `Init`; `Reset` clears trend, pivots, liquidity pools, and duplicate state.
Complexity is O(left + right) per closed bar, with constant additional state.

## Root market-direction readout

The root consumes the cached chart series without building a per-tick `MqlRates`
copy. It chronologically warms the engine from retained closed bars and advances
only when a new bar closes. For warm-up history, ATR is omitted from displacement
events (to avoid repeatedly recomputing historical ATR); current closed bars use
the cached ATR. BOS/CHoCH state is unaffected by that warm-up optimization.

The visible chart label combines the existing weighted D1/H4/H1 bias score (65%)
with the confirmed chart structure state (35%). This is a **confluence heuristic**,
not a probability, confidence estimate, or entry trigger. Explicit disagreement
between a non-neutral HTF bias and local BOS/CHoCH state produces `MIXED / CONFLICT`
and neutral direction rather than forcing a side. With only one valid source, the
label identifies the available context; missing structure data is shown rather than
silently counted as agreement. The readout does not loosen existing entry gates.

## Tests

`CArbSelfTest::T12_StructureCausality` exercises confirmation timing, HH, BOS,
CHoCH/invalidation, duplicate suppression, equal-high liquidity, sweep-versus-
breakout behavior. `tools/test_structure.py` independently checks the timing and
boundary contracts in CI. These checks do not prove MetaEditor compilation,
market replay correctness, predictive performance, or profitability.
