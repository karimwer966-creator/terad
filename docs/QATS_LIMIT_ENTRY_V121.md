# QATS v1.21 — LIMIT entry at the SMC zone

`MQL5/Experts/QuantumAutonomousTradingSystem.mq5` — `#property version "1.21"`.

**What changed:** the entry order. v1.20 bought or sold at market the moment an M5
setup scored high enough. v1.21 keeps the same detection, the same scoring, the
same guard chain and the same management, but the order that is sent is a
`BUY LIMIT` / `SELL LIMIT` resting at a strong SMC zone, waiting for the
retracement into it. Nothing about *whether* a setup is taken changed; only
*where* the fill happens.

**The honest status:** this is not a compile, not a Strategy Tester run and not a
forward test. The source builds cleanly (zero errors, zero warnings) with a host
C++ compiler against a typed MQL5 shim, and the whole EA runs inside an offline
broker simulator in both directions. **F7 in MetaEditor remains the build gate
and a DEMO chart remains the execution gate.** Both were unavailable here.

---

## 1. What was added

### 1.1 Inputs (7, in their own block after "5. position management")

| Input | Default | Meaning |
|---|---|---|
| `InpUseLimitEntry` | `true` | `false` = the v1.20 market entry, byte for byte |
| `InpLimitMaxDistATR` | `3.0` | refuse a zone farther than this × H1 ATR |
| `InpLimitExpiryMin` | `180` | resting time, `ORDER_TIME_SPECIFIED` |
| `InpLimitEntryMode` | `0` | `0` = zone midpoint, `1` = near edge |
| `InpLimitSLBufferATR` | `0.30` | stop beyond the far zone edge, × H1 ATR |
| `InpLimitMinRR` | `2.0` | reward:risk measured **from the limit price** |
| `InpLimitNeedPD` | `true` | SELL only in premium, BUY only in discount |

Declared inputs: 57 (50 before). `presets/Quantum_XAUUSD_PRODUCTION.set` ships all
seven at the compiled defaults; `tools/test_qats_limit_entry.py` fails if the two
ever disagree.

### 1.2 Functions (SECTION 20b, before SECTION 21)

The five required functions, plus the helpers that keep them readable:

```
CountMyPending           ZoneUnmitigated        ZoneOverlaps
PickEntryZone            LimitEntryPrice        LimitPriceInPD
BuildLimitPlan           PlaceLimitOrder        ManagePendingOrders
IsInvalidFillRetcode     IsPlacedOrDone         DeletePendingOrder
PendingOrderSetupTime    ZoneSourceName         LimitMoneyPerPriceUnit
```

### 1.3 Wiring

* `GuardBlocks` — the position cap is now `CountMyPositions() + CountMyPending()
  >= InpMaxOpenPositions`: a working limit occupies a slot, so the EA cannot
  stack ten limits and then fill them into ten positions.
* `ProcessSignal` — after the opposite-side exit, `if(canManage && InpUseLimitEntry)
  ManagePendingOrders(raw)`, then the unchanged guard chain, then either
  `PlaceLimitOrder` (limit path, journalled `LIMIT_PLACED` / `NOT_PLACED`) or the
  untouched `BuildTradePlan` + `ExecuteSignal`.
* `OnTradeTransaction` — `trades_<day>` and `g_tradesToday` move on
  `DEAL_ENTRY_IN` **only**, and only on the limit path (the market path still
  counts in `ExecuteSignal`, so nothing can be counted twice).

### 1.4 The limit itself

* **Zone choice:** OB+FVG overlap → OB alone → FVG alone; zones already mitigated
  by a closed H1 bar are skipped (`ZoneUnmitigated` scans shifts `from … 1`).
* **Price:** midpoint of the zone (mode 0) or 25 % inside the near edge (mode 1),
  normalised to the tick grid.
* **Rejected** if the zone is closer than `max(stops level, freeze level)`, if the
  market already passed it, or if it is farther than `InpLimitMaxDistATR` × H1 ATR.
* **P/D gate:** a SELL only at or above 50 % of the H1 dealing range, a BUY only at
  or below it.
* **Stop:** far zone edge ± (`InpLimitSLBufferATR` × ATR + spread), rounded away
  from the market, clamped by `InpMinStopPoints` / `InpMaxStopPoints`.
* **Target:** the nearest liquidity pool, offset 0.10 × ATR inside it; if that does
  not reach `InpLimitMinRR` (and `InpMinRR`) from the **limit** price, the order is
  not sent.
* **Filling:** `RETURN` → `IOC` → `FOK` on `TRADE_RETCODE_INVALID_FILL`.
  Success = `PLACED` or `DONE`; `PLACED` is verified by reading `OrdersTotal()`,
  not by trusting the retcode alone.
* **Expiry:** `ORDER_TIME_SPECIFIED`, now + `InpLimitExpiryMin` minutes.
* **Cancellation** by name: `EXPIRED`, `M5_CLOSED_BEYOND_SL`, `OPPOSITE_SIGNAL`,
  `PRICE_RAN_AWAY` (> 1.5 × `InpLimitMaxDistATR` × ATR), `SETUP_GONE`. Each one
  journals that *the daily trade cap is untouched*.

Every new line is prefixed `[QATS][LIMIT]` and carries entry / SL / TP / volume /
risk / zone source, or the rejection reason:

```
[QATS][LIMIT] PLAN direction=BUY symbol=XAUUSD bar=2024.03.25 13:00 setup=B-20240325-1200
   score=87 type=BUY_LIMIT entry=1859.90 sl=1857.52 tp=1864.66 tpSource=RR rr=2.00
   stopPts=238.0 zone=OB volume=0.21 risk=49.98 USD expiry=2024.03.25 16:00
[QATS][LIMIT] SEND direction=BUY filling=RETURN sent=true retcode=10008 order=1000001 price=1859.90 volume=0.21
[QATS][LIMIT] PLACED direction=BUY setup=B-20240325-1200 order=1000001 entry=1859.90 sl=1857.52
   tp=1864.66 volume=0.21 risk=49.98 USD rr=2.00 zone=OB
   (pending orders are not counted against the daily trade cap)
```

---

## 2. Self-review as required

### 2.1 Guards intact — the diff, not a claim

`git diff` on the EA deletes **five** existing lines in total:
`#property version`, `QATS_VERSION`, the input-cap line in `GuardBlocks`, and the
`EntriesAllowed` body (which now calls `GuardBlocks`, the function that already
held the whole chain — the chain itself is unchanged). Everything else is
additions.

`tools/test_qats_limit_entry.py` (96 checks, run in CI) asserts by name that these
are still present and still on the limit path: `VerifyAccountProtection`, the
daily loss lock, the drawdown halt, the cooldown, `InpMaxTradesPerDay`, the
spread-vs-stop guard, `IsXAUUSD`, `ReserveSignal`, `CalcPositionVolume`,
`EffectiveRiskPercent`, `OppositePositionOpen`, `SetupAlreadyTraded`, `InpDryRun`.
It also asserts that no order can be sent without a stop, that the stop comes from
the far zone edge and is clamped, and that `martingale` / `averaging` / `grid`
appear nowhere in the source.

### 2.2 `InpUseLimitEntry=false` reproduces v1.20

The false branch of `ProcessSignal` is the old code, verbatim: `BuildTradePlan` →
`ExecuteSignal`, still incrementing `g_tradesToday` inside `ExecuteSignal`.
`ManagePendingOrders` returns immediately, `OnTradeTransaction`'s new counter
branch is gated on `InpUseLimitEntry`, and `CountMyPending()` returns 0 when no
limit exists — so the position cap reads exactly as before. All the v1.20
scenarios still run with the switch off (`tools/qats_sim/qats_market.inc` pins it)
and are unchanged: 45 of the 51 scenarios, same results as v1.20, plus the mirror
proof which is 0 mismatching bars over 14,040 bars in both directions.

### 2.3 A cancelled or expired limit never consumes the daily cap

Three independent reasons:

1. `g_tradesToday` / `trades_<day>` are incremented in `OnTradeTransaction` on
   `DEAL_ENTRY_IN` only. A cancellation produces `TRADE_TRANSACTION_ORDER_DELETE`,
   which never reaches that branch.
2. `PlaceLimitOrder` does **not** call `MarkSetupTraded` — only the fill does, in
   `OnTradeTransaction`. A cancelled limit leaves its setup tradable.
3. `DeletePendingOrder` re-runs `VerifyAccountProtection` before deleting, so a
   cancellation can never act on an unauthorized terminal.

The `limit_cancel_*` scenarios run this end to end in both directions: one
`[QATS][LIMIT] CANCELLED … reason=PRICE_RAN_AWAY`, `g_tradesToday == 0`, the
persisted `trades_<day>` still 0, `SetupAlreadyTraded()` still false, no fill.

### 2.4 `ReserveSignal` must not block the next M5 bar after a cancellation

**Report.** `ReserveSignal` refuses a reservation when the stored previous
`signalBar` is `>=` the new one. The identity QATS reserves is
`a.signalBar = iTime(_Symbol, PERIOD_M5, 0)` — the **current** M5 bar — set in
`AnalyzeMarket` on every new bar. So the reserved identity advances once per M5
bar no matter what happens to any order: a cancellation at bar *N* leaves the
reservation at *N*, and the next bar is *N+1*, which is strictly greater. A
cancelled limit therefore cannot block a legitimate new signal on the next bar,
and that is *by construction*, not by a lifetime.

That property is now pinned, not assumed:
`tools/test_qats_limit_entry.py` asserts that the reserved identity is the current
M5 bar, and the `limit_cancel_*` scenarios assert `SetupAlreadyTraded()` is still
false after the cancellation.

**One real edge remains, and it is pre-existing (v1.20, not introduced here).**
The reservation is a monotonic `>=` test, so two signals *inside the same M5 bar*
cannot both reserve. On the limit path that is the desired behaviour — one bar
produces at most one plan. But there is one way an operator can lose a bar: if a
limit is cancelled by `M5_CLOSED_BEYOND_SL` and the EA re-plans on the *same* bar
afterwards, the re-plan is refused. `ManagePendingOrders` runs before the entry
chain, so the slot is freed on the same bar — but the reservation for that bar is
already spent by the placement.

**Proposed fix (not applied, so as not to weaken duplicate protection without a
decision):** give the reservation an explicit order scope. Reserve
`(signalBar, "limit:<ticket>")` on placement; in `DeletePendingOrder`, clear the
reservation **only if** the stored identity is that exact `limit:<ticket>` and the
signal bar is the current one. Then:

* two market signals in one bar are still refused (identity unchanged),
* a re-plan after a cancellation on the same bar is allowed exactly once,
  because the cancellation cleared its own scope,
* a second cancellation has nothing left to clear, so the protection cannot be
  cleared in a loop.

It is deliberately **not** implemented in v1.21: it changes `ReserveSignal`'s
contract, which v1.20's duplicate protection depends on. Cost of leaving it: at
most one missed re-entry per cancellation, on the bar of the cancellation, with
the setup still tradable on the next bar.

---

## 3. Compile warnings

**None known, and none claimed.** The evidence is:

* strict host build (`-Werror -Wall -Wextra -Wshadow -Wconversion`), zero
  warnings, 57/57 build-gate checks;
* the MQL5-only lint (`->` on a struct, string concatenation, `string(side)`
  casts) finds nothing — it caught and this change fixed three real
  struct-pointer dereferences that would have been F7 errors;
* `tools/verify_quantum_ea.py` PASSED, `tools/test_quantum_compile_regressions.py`
  OK.

This is **not** a MetaEditor compile. MetaEditor's own warning set differs, and
only F7 can produce the "0 errors, 0 warnings" line the runbook requires.

## 4. Assumptions

1. `ORDER_TYPE_BUY_LIMIT` / `SELL_LIMIT` with `ORDER_TIME_SPECIFIED` are accepted
   by the target broker. If a broker rejects the expiration, the send fails and is
   journalled `NOT_PLACED` with its retcode — the EA does not fall back to market.
2. The stops/freeze levels returned by `SYMBOL_TRADE_STOPS_LEVEL` /
   `SYMBOL_TRADE_FREEZE_LEVEL` are meaningful on the target server; the
   "zone closer than the broker allows" rejection depends on them.
3. The chart is drawn from the **bid**, so a SELL limit and a SELL stop must carry
   one spread to sit at the intended *chart* level. This was a real bug found by
   the mirror test and fixed (see below); it assumes the usual bid-chart
   convention already documented in SECTION 16.
4. The daily cap semantics are "filled entries per server day". A limit placed
   yesterday and filled today counts today.

## 5. Unverifiable here

| Item | Why it cannot be verified in this environment |
|---|---|
| F7 compile, 0 errors / 0 warnings | no MetaEditor |
| Server-side fill of a limit at the zone | no MT5 terminal or live server |
| `ORDER_TIME_SPECIFIED` accepted by the broker | broker-specific |
| Broker stops/freeze level behaviour | broker-specific |
| Slippage / requote on limit fill in real conditions | needs a live/demo server |
| Strategy Tester result of the limit entry | needs MT5 |
| Whether the limit entry improves expectancy | **no** — the offline simulator proves mechanics and symmetry only, and the v1.20 study already showed negative expectancy in-sample on this data |

## 6. Evidence collected

| Suite | Result |
|---|---|
| `tools/test_qats_limit_entry.py` (new) | **96 / 0** — every contract in sections 2.1–2.4 above |
| `tools/test_qats_dual_direction.py` | **79 / 0** — 309 unit checks, 51 scenarios, 12 mirrored pairs, 14,040-bar symmetry replay, ASan + UBSan |
| `tools/test_qats_native_build.py` | 57 / 0 — strict host build of the whole `.mq5` |
| `tools/verify_quantum_ea.py` | PASSED (structural only) |
| `tools/test_quantum_compile_regressions.py` | OK |
| `tools/test_xau_execution_policy.py` | OK (24 score/direction, 8 veto, 26 guard cases) |
| `tools/test_quantum_account_policy.py` | OK (16) |
| `tools/test_qats_journal_report.py` | 33 / 0 |
| `tools/check_release_gate.py` | GO, 0 warnings |

### The symmetry bug this work found

The mirror test compares a BUY run against a SELL run on a price series reflected
about `K = 400000`. It initially disagreed on 54 bars: on `2024.06.17 14:35` a
SELL limit was `PLACED` where its BUY twin was `REJECTED`. Cause: `LimitPriceInPD`
compared an **ask-quoted** entry against an H1 dealing range built from **bid**
closes, and the SELL entry/stop were not spread-adjusted. Both were real
asymmetries; both are fixed (the SELL price carries one spread, and the P/D test
compares the chart level). After the fix: **0 mismatching bars out of 14,040**,
4 trades versus 4 mirrored trades with identical mirrored P/L.

### Scenarios added

| Scenario | What it proves |
|---|---|
| `limit_entry_buy` / `_sell` | the order is a `*_LIMIT` at the zone with its own SL/TP, on the tick grid, RR ≥ `InpLimitMinRR`, inside the stop bounds, expiry in the future; no market order is sent; the cap stays 0 |
| `limit_cancel_buy` / `_sell` | price runs away from the zone → `CANCELLED … reason=PRICE_RAN_AWAY`, cap stays 0 in memory **and** in the persisted GV, the setup stays tradable |
| `limit_fill_buy` / `_sell` | the retracement fills the order at the limit price with its own SL/TP → **exactly one** trade counted, exactly one position, never a second one for the same setup |

All six run in both directions with mirrored numbers, and again under
AddressSanitizer + UBSan.
