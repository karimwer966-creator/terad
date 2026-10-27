# QSMC v6.6.6 — Production checklist (go / no-go, observation, rollback)

This is the operational document. `docs/QSMC_BUILD_AND_RUN.md` says **how to
install**; this one says **when it is allowed to run next to money, what to watch
in the first 24 hours, and how to back out in under a minute**.

One sentence about scope, because it decides every threshold below:

> **This layer never places, modifies or closes an order.** It arbitrates signals,
> deduplicates them, publishes them to the Journal / alert channels / CSV journal /
> GlobalVariables, and measures whether the market data it used was trustworthy.
> If a build of this layer can reach the trade API, it is not this layer.
> `tools/check_release_gate.py` G4 makes that a checked property, not a promise.
>
> **Execution, since v6.6.6, is a separate opt-in program** —
> `MQL5\Experts\QSMC_AutoTrader.mq5` — and it is the only file allowed to reach the
> trade API (G4 allowlist, G8 checks how it ships). It reads the published CORE
> signal buffers and changes no gate. If you do not attach it, nothing in this
> release can trade. Guide: `docs/QSMC_AUTOTRADER.md`.

---

## 0. What "production ready" means here — and what it does not

| Ready means | Ready does NOT mean |
| --- | --- |
| The layer cannot trade or touch the network (checked by G4) | The strategy is profitable — that is a backtest question, not a deployment one |
| Every per-bar log line is behind `InpArbVerboseLog` (checked by G5) | The code has compiled once on *your* terminal — see §2 |
| One version string is used by code, banner and docs (checked by G1) | That a green CI run is a compile: it is not, there is no MetaEditor in CI |
| Alerts deduplicate across charts of the same symbol | Alerts are globally unique across accounts/terminals |
| A crash cannot wedge later bars (lock TTL 7 days, per-bar keys) | That the terminal must not be restarted mid-bar (it can, §7) |

---

## 1. The mechanical go / no-go — one command

```bash
python3 tools/check_release_gate.py
```

`GO` / `NO-GO` on the last line, exit code to match. It checks:

| Check | Property |
| --- | --- |
| G1 | `#define QSMC_VERSION_TEXT`, `#property version`, the runtime banner and the runbook title all name the **same** build |
| G2 | 18 headers + host + indicator + probe + script + feeder EA + execution EA all present — a half-copied install is a compile error three files deep |
| G3 | all 40 inputs are declared **and** documented; the chatty ones (`InpArbVerboseLog`, `InpArbCSVLog`) default to `false` |
| G4 | no trade API in the layer (headers + indicator + probe) and none in the feeder; the **only** file allowed to trade is `QSMC_AutoTrader.mq5`; `Alert`/`SendNotification`/`PlaySound` only inside `CAlertManager`; file writes only in `CStatsLogger`; network only in the optional feeder |
| G5 | no `Print`/`Alert` on the per-bar path without an `InpArbVerboseLog` guard |
| G5b | the feeder's `InpUrl1/2/3` and `InpApiKey` default to empty — it ships inert |
| G6 | no `TODO` / `FIXME` / "not implemented" left in the shipped path |
| G8 | the execution companion ships `InpEnableTrading=false`, `InpDryRun=true`, `InpDemoOnly=true`, clamps risk to 1% of equity, has no lot doubling, and its only position modify is the break-even move |
| G7 | CI actually runs this script (a gate nobody runs is a suggestion) |

Run the other four too — the gate does not duplicate them:

```bash
python3 tools/mql5_rules.py --quiet && python3 tools/static_check.py
python3 tools/test_arbiter.py && python3 tools/test_scanners.py
python3 tools/test_quant_stats.py && python3 tools/test_structure.py
python3 tools/test_early_break.py && python3 tools/test_zone_scoring.py
python3 tools/test_edgebook_contract.py
python3 tools/test_autotrader_contract.py
python3 tools/check_scenario_geometry.py
```

---

## 2. Install verification — the five minutes that decide the rest

1. **Open the Data Folder** (MetaTrader 5 → *File → Open Data Folder*) and confirm
   `MQL5\Include\QSMC\` contains **exactly** the 18 `.mqh` files of `v6.6.6`.
   `check_release_gate.py` G2 proves the *repo* is complete; this proves the *copy* is.
2. **F7 in this order**, one at a time, reading the result pane each time:
   `MQL5\Scripts\QSMC_ArbiterTest.mq5` → `MQL5\Indicators\QSMC_ScannerProbe.mq5` →
   `MQL5\Experts\KLJ_DataFeeder.mq5` → `MQL5\Indicators\nadir2.mq5` →
   `MQL5\Experts\QSMC_AutoTrader.mq5` (only if you intend to execute).
   Acceptable warning: *`no indicator plot defined for indicator`* (the probe draws no
   plot). **Anything else is a stop** — post the whole line, not "it has an error".
3. **The banner is the version check.** Compile messages lie when a stale copy wins;
   the log does not. Load the indicator and the first `[QSMC_ARB]` line must read:
   ```
   [QSMC_ARB] v6.6.6 arbitration layer ON | preset INTRADAY (M15-H1) | gates 10 ... | on XAUUSD M15
   ```
   Any other version → you are running a stale copy of `Include\QSMC` (or of the
   indicator). Close the terminal, re-copy, recompile. Do not continue.
4. **One-shot self-test**: *Navigator → Scripts → `QSMC_ArbiterTest`* →
   `RESULT: 0 failed.` on its single comment line.
5. `InpArbGateCore=false`, `InpArbGateTactical=true`, `InpArbMinBars=120`,
   `InpArbCSVLog=false`, `InpArbVerboseLog=false`, `InpArbPopup=true`,
   `InpArbPush=false` — unless the table in §5 says you changed one on purpose.

**Stop conditions for §2:** any compile error, any version mismatch in the banner, any
`alloc/free` inequality at detach, a self-test with a failure.

---

## 3. First hour on a live (or demo) chart

Watch the Experts tab. Healthy looks like this — and only like this:

| Time | Expected line | Why it is the right line |
| --- | --- | --- |
| attach | `[QSMC_ARB] v6.6.6 arbitration layer ON \| ... \| on XAUUSD M15` | version, preset, gate count and **the instrument the thresholds are measured against**, in one line |
| attach | `[QSMC_ARB] preset INTRADAY (M15-H1): exec M15, H4 from H1, D1 from H4` | the resample map actually chosen |
| per closed bar | *nothing at all* unless `InpArbVerboseLog=true` | silence is the designed behaviour |
| on a published signal | `[QSMC_SIG] ...` with `(deduped n)` / `(cooldown n)` counters | the arbiter, not the raw signal source |
| detach | `[QSMC_ARB] alloc/free: 5/1 ... => no leak` | the counters moved, nothing leaked |

Do these three deliberate tests inside the first hour (cheap, and they are the only
ones that prove the safety properties are live rather than theoretical):

1. **Duplicate test** — open the same symbol+TF on a second chart with the indicator.
   Expected: the second chart claims the same GlobalVariable namespace and the popup
   fires **once** for a given bar on one chart only. If both alert, `InpArbUseGlobalVars`
   is off.
2. **Data-loss test** — disable *Algorithmic trading* / disconnect, or pick a symbol
   with no history. Expected: `[QSMC_ARB] ... data NOT ready: <reason>` once, then
   silence; the panel shows `data not ready`; **no** signal is published while the
   series are stale. A layer that keeps alerting on stale bars is a layer you delete.
3. **Restart test** — detach the indicator mid-bar and re-attach. Expected: the same
   `bar_time` is not re-alerted (the lock is per `symbol + bar_time`, so a crash can
   block **that** bar and never a later one).

---

## 4. First 24 hours: what to measure, and when to abort

| Metric | How to read it | Abort threshold |
| --- | --- | --- |
| Alerts per hour | count `[QSMC_SIG]` lines / hour | > 30/h on one symbol+M15 → the cooldown/distance gates are mis-tuned; set `InpArbGateTactical=true` and raise `InpArbCooldownBars` |
| Duplicate rate | the `(deduped n)` counter | rising while `published n` is flat → the key is too specific: check `InpArbDedupeRing` (256) and `InpArbMinAlertDistanceATR` |
| Journal volume | size of the Experts log | > ~2 MB/day on one chart → `InpArbVerboseLog` is on, or a data source is flapping (§7) |
| Memory | Task Manager, `terminal64.exe`, before/after 24 h | > ~20 MB of growth per chart per day → stop and capture `[QSMC_ARB] alloc/free` at detach |
| `alloc/free` at detach | the log line | unequal → **stop**; report with the `[QSMC_MD]` counts (`5/1` here) |
| Refusals | probe: `refused N/M` | `refused == scanned` → the bars are too short: `InpProbeBars=200`, `min_bars` |
| Data freshness | `[QSMC_DATA] refresh ... 4073/4064` repeats | ≥ 3 in a row on the same symbol → the feed, not the logic |

The `QSMC_ScannerProbe` may stay attached for the whole 24 h: it holds no position,
never alerts, and its only cost is one timer and a `Comment()` string. Remove it when
you have the numbers you wanted.

---

## 5. Alert routing — decide this before you need it

| Channel | Input | Default | Behaviour |
| --- | --- | --- | --- |
| Popup | `InpArbPopup` | **true** | `Alert()`, once per published signal (the arbiter publishes at most one row per bar) |
| Push (mobile) | `InpArbPush` | false | `SendNotification()` — enable only after you have read the 24 h rate |
| Sound | `InpArbSound` | false | `PlaySound()` |
| CSV journal + EdgeBook | `InpArbCSVLog` | false | Versioned append-safe signal CSV and completed-outcome ledger in terminal-local `MQL5\Files`; see `docs/QSMC_EDGEBOOK.md` |
| Cross-chart claim | `InpArbUseGlobalVars` | true | GlobalVariable per `symbol + bar_time`, TTL `QSMC_GV_TTL_SEC = 604800` (7 days) |
| Per-bar dump | `InpArbVerboseLog` | false | every gate verdict, every closed bar. Debug only |

`Alert`, `SendNotification` and `PlaySound` exist in **one** file
(`QSMC_AlertManager.mqh`), which is why a reviewer can certify what a build can do to
your terminal by reading one file. The gate enforces that it stays that way.

A stale lock can only block the bar it was written for. If you ever need to clear the
namespace by hand (after changing the key scheme): *Tools → List of Global Variables* →
delete the `QSMC_*` entries. The terminal, not the indicator, owns that list.

---

## 6. Time-base caveat — the one thing a demo cannot teach you

Bars, dedupe keys and cooldown windows are all counted in **server time**
(`TimeCurrent()` of the feed), while sessions and your expectations are often in UTC or
in exchange local time. A demo run on a broker whose server is UTC+2 behaves differently
from a live crypto feed on UTC — the *logic* is identical, the *clock* is not.

Measure it, don't assume it: `QSMC_ScannerProbe` prints `basis SERVER|UTC` in its init
line, and `InpProbeTf` with several timeframes makes the mismatch obvious. Fix the
mismatch at the chart/EA level (session inputs, `InpArbSessionStartHour` /
`InpArbSessionEndHour`), never by editing bar timestamps.

---

## 7. Failure modes and operator actions

| Symptom | Meaning | Action |
| --- | --- | --- |
| Banner version ≠ repo version | stale copy in the Data Folder (a second copy of a header can shadow the right one — CI checks the repo for duplicate basenames, not your folder) | close terminal, re-copy §1 of `QSMC_BUILD_AND_RUN.md` |
| `cannot include QSMC/...` | the include root is not the Data Folder's `MQL5\Include` | fix the folder, not the code |
| `no indicator plot defined for indicator` | expected for the probe | ignore |
| `reference cannot used` / `not a pointer type` / `unknown type 'u'` | a dialect violation of D1/D2/D3/D12 | recompile; if you wrote it, follow the rule in `tools/mql5_rules.py` before F7 |
| `[QSMC_ARB] ... data NOT ready: ...` on every bar | the feed or the timeframe is unavailable | check the symbol has history for the exec TF; the layer is correct to stay silent |
| `[QSMC_MD] ... 4073` / `4064` repeating | copy-rate limits / history not loaded | raise `InpProbeBars`/`min_bars`, lower the symbol count, or move the fetcher into the `Experts` feeder EA |
| Journal flooding | `InpArbVerboseLog` left on | turn it off (default is off — G3); the gate blocks the per-bar paths that could do it without asking |
| Alerts stop after a terminal crash on the current bar | a lock for that `bar_time` survived | expected and bounded: only that bar is blocked; the sweep and the 7-day TTL clean the rest |
| `alloc/free: a/b` unequal | a leak in this layer | stop using it, report both numbers plus the `[QSMC_MD]` line |
| `unbalanced new/delete` in `static_check.py` | a leak or a double-free found before F7 | fix the owner, or add the file to `EXTRA` if it is genuinely a program file |

---

## 8. Rollback — under a minute, two levels

**Level 1 — disable the layer (recommended first move).**
Set `InpArbEnabled=false`, recompile `nadir2.mq5`, reload the chart. The host still
calls the entry points, each one returns "disabled" immediately, and signals go back to
the pre-v6.6.0 path. The marker comment `// v6.6.0 QSMC_ARB_PATCH_MARKER` **stays** —
`apply_qsmc_arb_patch.py` is idempotent because of it, and renaming it would make the
next `--check` lie.

**Level 2 — remove the subsystem.**
Delete `MQL5\Include\QSMC`, the compiled `QSMC_ScannerProbe.ex5`,
`QSMC_ArbiterTest.ex5`, `KLJ_DataFeeder.ex5`; recompile `nadir2.mq5`. Then in
*Tools → List of Global Variables* delete the `QSMC_*` entries so no stale claim or
counter is left behind.

Rollback is trivially safe **because the layer never touches orders** — that is the
design reason the whole module is an indicator include rather than an EA.

---

## 9. Known limits of this release (accepted, not hidden)

| Limit | Impact | Plan |
| --- | --- | --- |
| Zone scoring is wired to the root tactical zone-reaction candidate builder | this repository has no other `SSignalCandidate` producers for CORE/ZRE/RXN; any external/legacy entry publishers are outside this coverage | inspect those integrations before claiming all system entries are scored |
| EdgeBook restart recovery depends on available chart history | if the setup bar is unavailable or replay data is invalid, it is marked AMBIGUOUS and excluded from win/loss rates | verify replay-history depth and gap handling on MT5; see `docs/QSMC_EDGEBOOK.md` |
| EdgeBook bounded memory index (12,000 outcomes / 128 keys) | capacity exhaustion fails closed and withholds trusted rates | archive/rotate only with an explicit migration and dedupe plan |
| No MetaEditor in CI — F7 is a manual step | "green" ≠ "compiles" | §2 step 2 is the only compile proof. Run it on every build you ship |
| `QSMC_Scanners.mqh` has one host (the probe), not the main indicator | its numbers are exercised by 40 offline assertions, not by the panel | Phase 7: render `QSC_*` rows in the `CFX*` panel, then wire the scanner output into the gate counters |
| `nadir2.mq5` (39 792 lines) stays dirty of D6/D11 style debt | legacy `iOpen`/`time[0]`, reused locals in the host; the *subsystem* is clean | decomposition, layer by layer, with `ZRE → RXN → SigLog`; keep the marker |
| The self-test geometry is H1-shaped (`atr≈93, range≈1000`) | running the arbitration on a 1-point range scenario would *look* like a bug | never tune `InpArbMinATRPoints` from the self-test; read `check_scenario_geometry.py` instead |
| Tactical path cannot publish `CONFIRMED` by default (`InpArbTacticalMayConfirm=false`) | by design: MTF tactical is gated, not promoted | flip only if a 24 h run shows a systematic under-call |
| Sessions, holidays and venue rules are not modelled here | a `REJECT` in that area is expected, not a fault | they live in `QSMC_Gates.mqh` and the feed contract `docs/KLJ_V6.6.0_PART_C.md` §7.6 |

---

## 10. Sign-off

```
[ ] tools/check_release_gate.py  -> GO (0 blocks)
[ ] static_check.py / mql5_rules -> no errors (warnings read, not ignored)
[ ] test_arbiter.py 22/0 | test_scanners.py 40/0 | geometry OK
[ ] F7 on QSMC_ArbiterTest.mq5   -> 0 errors
[ ] F7 on QSMC_ScannerProbe.mq5  -> 0 errors, "no indicator plot" acceptable
[ ] F7 on KLJ_DataFeeder.mq5     -> 0 errors
[ ] F7 on nadir2.mq5             -> 0 errors
[ ] banner reads v6.6.6 on the live chart
[ ] QSMC_ArbiterTest -> RESULT: 0 failed.
[ ] alloc/free equal at detach
[ ] first-hour tests 1-3 (§3) done and behaving
[ ] 24 h metrics (§4) recorded, no abort threshold crossed
[ ] InpArbVerboseLog back to false, InpArbPush still false unless chosen
[ ] rollback §8 rehearsed once on a demo chart
```

Signed off means: this build may sit on a live chart and **alert** a human. It does not
mean it may decide size, entry or exit — those decisions belong to the EA, and the
contract for what the layer may and may not publish is `docs/KLJ_V6.6.0_PART_C.md`
§7.6.
