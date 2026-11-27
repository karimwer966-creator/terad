# Buffer contract — `nadir2.mq5` → `QSMC_AutoTrader.mq5`

The indicator and the execution companion share **no code that matters**. They
share 27 `double` arrays. This document is that contract.

Until v6.6.25 the contract existed only as `#define`s in one file, a
`SetIndexBuffer` block in another, and a few comments. If a buffer index moves,
nothing in the product fails loudly — the EA simply reads the wrong number and
trades it. This file is the written contract, and
`tools/test_buffer_contract.py` fails the build if the document and the source
disagree in either direction.

> **Status: source-contract ready. Neither file has been compiled (F7) and no
> Strategy Tester evidence exists. This document describes the source, not a
> verified runtime.**

---

## 1. Ground rules

**Indexing.** Every calculation buffer is chronological, not series:
`ArraySetAsSeries(..., false)` for all of them (`nadir2.mq5:15526-15545`). The EA
sets its own copy to series (`QSMC_AutoTrader.mq5:2311-2316`) and asks
`CopyBuffer` for `count` values, so shift 0 is the forming bar and shift 1 is the
last closed bar.

**Where a value sits.** A signal value is written on the **closed signal bar**,
once, after the bar closed (`nadir2.mq5:13870-13871`). The EA reads shift 1.

**"Nothing here".** Two different conventions, and mixing them up is the classic
failure:

| buffers | empty value | source |
|---|---|---|
| 0–6 (plotted) | `EMPTY_VALUE` | `PlotIndexSetDouble(q,PLOT_EMPTY_VALUE,EMPTY_VALUE)` `nadir2.mq5:15480` |
| 7–26 (calculations) | **`0.0`** | `nadir2.mq5:13870` *"0 = no signal"*; `QSMC_AutoTrader.mq5:176-178` *"0.0 means 'not yet written'"* |

`0.0` doubles as "this build never wrote the buffer", which is what makes the EA
backward-compatible with an older indicator: the classification copy is optional
and its failure degrades to class 0 = STRONG-only (`QSMC_AutoTrader.mq5:2323`).

**Declared size.** `#property indicator_buffers 27` (`nadir2.mq5:666`),
`#property indicator_plots 7` (`:667`). Indices **0–26, contiguous, no gaps** —
asserted by the gate.

---

## 2. The table

`EA reads` is the literal set of `#define QSMC_BUF_*` numbers in
`MQL5/Experts/QSMC_AutoTrader.mq5:169-188`. 13 of 27 are read.

| Idx | Buffer array | Plot | EA reads | Meaning | Values |
|---|---|---|---|---|---|
| 0 | `BufEmaFast` | 1 line | no | EMA of close, `InpEMAFast` | price, `EMPTY_VALUE` when unset |
| 1 | `BufEmaSlow` | 2 line | no | EMA of close, `InpEMASlow` | price |
| 2 | `BufVWAP` | 3 line | no | session VWAP | price |
| 3 | `BufEntryBuy0` | 4 arrow 233 | no | confirmed BUY entry mark | entry price, else `EMPTY_VALUE` |
| 4 | `BufEntrySell0` | 5 arrow 234 | no | confirmed SELL entry mark | entry price |
| 5 | `BufPrevBuy0` | 6 arrow 108 | no | preview BUY mark (forming bar) | entry price |
| 6 | `BufPrevSell0` | 7 arrow 109 | no | preview SELL mark | entry price |
| 7 | `BufSigCoreDir` | — | **yes** `QSMC_BUF_CORE_DIR` | **CORE direction — this is the trade** | `+1` buy, `-1` sell, `0` none |
| 8 | `BufSigCoreEntry` | — | **yes** `QSMC_BUF_CORE_ENTRY` | CORE planned entry | price, `0` none |
| 9 | `BufSigCoreSL` | — | **yes** `QSMC_BUF_CORE_SL` | CORE stop loss | price, `0` none |
| 10 | `BufSigCoreTP1` | — | **yes** `QSMC_BUF_CORE_TP1` | CORE target 1 | price, `0` none |
| 11 | `BufSigCoreTP2` | — | **yes** `QSMC_BUF_CORE_TP2` | CORE target 2 | price, `0` none |
| 12 | `BufSigCoreTP3` | — | **yes** `QSMC_BUF_CORE_TP3` | CORE target 3 | price, `0` none |
| 13 | `BufSigZREDir` | — | no | ZRE direction | `+1`/`-1`/`0` |
| 14 | `BufSigZREEntry` | — | no | ZRE entry | price |
| 15 | `BufSigZRESL` | — | no | ZRE stop | price |
| 16 | `BufSigZRETP1` | — | no | ZRE target 1 | price |
| 17 | `BufSigZRETP2` | — | no | ZRE target 2 | price |
| 18 | `BufSigZRETP3` | — | no | ZRE target 3 | price |
| 19 | `BufSigCoreVerdict` | — | **yes** `QSMC_BUF_CORE_VCODE` | per-closed-bar CORE verdict code | see §4 |
| 20 | `BufSigZREVerdict` | — | **yes** `QSMC_BUF_ZRE_VKIND` | ZRE verdict kind | `+1` BUY, `-1` SELL, `0` NO TRADE |
| 21 | `BufSigCoreScore` | — | **yes** `QSMC_BUF_CORE_SCORE` | confidence score | `0`–`100`, `0` none |
| 22 | `BufSigCoreClass` | — | **yes** `QSMC_BUF_CORE_CLASS` | unified class | `0` none, `1` WEAK, `2` MODERATE, `3` STRONG |
| 23 | `BufSigCoreReliability` | — | **yes** `QSMC_BUF_CORE_REL` | reliability | `0`–`100`, `0` none |
| 24 | `BufSigCoreRR1` | — | **yes** `QSMC_BUF_CORE_RR1` | reward:risk to TP1 | ratio, `0` none |
| 25 | `BufSigCoreRiskMult` | — | **yes** `QSMC_BUF_CORE_RISKMUL` | risk multiplier the indicator picked | `0.25` / `0.50` / `1.00` |
| 26 | `BufSigCoreChain` | — | **no** | chain **kind label** | `0` none/switch OFF, `1` REVERSAL, `2` CONTINUATION |

Buffers **13–18 are never read by the EA** by design: `nadir2.mq5:14618` —
*"ZRE (src==1) has no class: the EA never executes ZRE, so 21-25 stay 0 for ZRE."*
Buffers **0–6 are display only** and carry no execution meaning.

---

## 3. Who writes what

All of 7–26 are written from **one** registration path, so they can never
disagree with each other:

```
SigLog_BufRegister(bar_time, src, buy, e, sl, t1, t2, t3, rates_total,
                   score, cls, reliability, rr1, chain)     nadir2.mq5:14649
   ├─ SigLog_BufWrite(idx, src, dir, e, sl, t1, t2, t3)     :14706  -> 7-12 (src 0) / 13-18 (src 1)
   ├─ if(src==0) SigLog_BufWriteClass(idx, ...)             :14707  -> 21-25
   └─ if(src==0) SigLog_BufWriteChain(idx, chain)           :14708  -> 26
```

| buffers | writer | line |
|---|---|---|
| 0–2 | `FillEMAAndVWAP()` | called from `OnCalculate()` |
| 3–6 | `EntryMarkWriteAt()` | `:14625` region |
| 7–18 | `SigLog_BufWrite()` | `:14587` |
| 19 | `DiagPublishCoreState()` | `:21125` |
| 20 | ZRE verdict publish | `:40154` |
| 21–25 | `SigLog_BufWriteClass()` | `:14619` |
| 26 | `SigLog_BufWriteChain()` | `:14634` |
| all, on purge | `SigLog_BufZero()` → writes 7–18, 21–25 **and** 26 back to 0 | `:14640` |

The caller that publishes a confirmed CORE signal is `nadir2.mq5:14998`, which
passes `chain = InpAllowContinuationChain ? (continuation ? 2 : 1) : 0`
(`:15006-15007`).

---

## 4. Buffer 19 — verdict codes

Written once per closed bar by `DiagPublishCoreState()` (`:21104`), from the
immutable journal rather than a display flag:

| code | meaning |
|---|---|
| 0 | nothing |
| 1 | a signal was **published** on this bar |
| 2 | an active setup exists |
| 3 | confirmation pending, or a valid setup |
| 10–34 | the top gate-audit blocker, from `DiagBlockerCode()` (`:21064`) |

The blocker set is 26 distinct codes: 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 (and 0 for "no
blocker"). Examples: 12 = *no confirmed liquidity sweep*, 20 = *geometry: RR1*,
23 = *score: confidence*.

The same code is mirrored to a `GlobalVariable` (`:21128`) for EAs without an
`iCustom` handle; the buffer is authoritative when the GV bridge cannot match an
instance (`QSMC_AutoTrader.mq5:175-178`).

---

## 5. Buffer 26 is a label, not a gate

This is the part that is easy to get wrong, and it was got wrong once already.

`InpAllowContinuationChain` (default **OFF**) lets a with-trend BOS with no
qualifying sweep form a CONTINUATION chain. When such a signal is confirmed it is
published **through the same registration call as every other CORE signal**, so:

- **buffers 7–12 carry it exactly like a REVERSAL signal**, and the EA executes it
  through `QSMC_BUF_CORE_DIR` (`QSMC_AutoTrader.mq5:2317`);
- **buffer 26 only says which kind it was** — `2` for CONTINUATION, `1` for
  REVERSAL, `0` when the switch is OFF.

The EA does **not** read buffer 26, and it should not. Buffer 26 is
classification output for the operator and for offline analysis
(`docs/QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md:123`). Wiring a display-only export
into the execution gate would mean the EA re-derives a decision the indicator
already made, which is the failure mode `QSMC_AutoTrader.mq5:181-183` exists to
prevent.

**Consequence for a beta trial:** turning `InpAllowContinuationChain` ON changes
what the EA trades. It is not a display-only switch. Read buffer 26 (or the
SigLog CSV column `causal_chain`) afterwards to split the results.

### 5.1 Export-only buffers — a decision, not an omission

Seven of the twenty-seven buffers have **no reader in the EA**, and that is the
intended state rather than unfinished work:

| Buffers | Name | Why they stay unwired |
|---|---|---|
| 13–18 | `BufSigZREDir/Entry/SL/T1/T2/T3` | **the EA never executes ZRE.** `nadir2.mq5:14618` says so: *"ZRE (src==1) has no class: the EA never executes ZRE, so 21-25 stay 0 for ZRE."* They are the ZRE leg's full trade geometry, published so an operator or an offline study can read it without re-deriving it |
| 26 | `BufSigCoreChain` | a **kind label** for a signal the EA already receives through buffer 7. Reading it in the execution path would make the EA re-derive a decision the indicator already made |

Calling these *export-only* is precise about what is being claimed:

* they **are** written, on every closed bar, by the same registration path as
  everything else (§3), so they are never stale relative to buffers 7–12;
* they are **not** inputs to any order decision, any gate, or any alert;
* nothing in this repository plans to wire them. Wiring one is a change to what
  the EA trades and needs its own approval, its own preset and its own tester
  measurement — not a one-line `CopyBuffer`.

If you are looking for a place to add a reader: **do not add it here.** The
reason the EA reads exactly 13 of 27 buffers is that those 13 are the decision
the indicator made, and the other 14 are either display (0–6), the unexecuted ZRE
leg (13–18), or labels (26). `QSMC_AutoTrader.mq5:181-183` exists to stop exactly
this kind of second-guessing.

`tools/test_buffer_contract.py` block **B7** fails if any of the seven grows an
EA-side reader, and block **B9** fails if this section stops saying so — so the
decision cannot quietly become an accident.

---

## 6. Compatibility rules for anyone changing this

1. **Never renumber an existing buffer.** Append. `indicator_buffers` and the
   `:666` comment go up together.
2. **A new buffer defaults to `0.0` and must stay `0.0` when its switch is OFF.**
   That is what keeps the flags-OFF output of buffers 0–25 byte-identical across
   releases, and it is how the EA tolerates an older indicator.
3. **`SigLog_BufZero()` must zero the new buffer too**, or a purged bar keeps a
   stale value.
4. **Buffers 7–12 are the money path.** Anything that changes what lands there is
   a trading-logic change, not a plumbing change.
5. Update this table and `tools/test_buffer_contract.py` in the same commit. The
   gate reads this file; a source change without a table change fails the build.

---

## 7. Cross-references

- How the flags-OFF A/B is produced: `MQL5/Scripts/QSMC_BufferDump.mq5`
- Risk inputs that consume buffers 21–25: [`EA_RISK_INPUTS.md`](EA_RISK_INPUTS.md)
- F7 and Tester plan: [`QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md`](QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md)
- The gate that enforces this file: `tools/test_buffer_contract.py`
