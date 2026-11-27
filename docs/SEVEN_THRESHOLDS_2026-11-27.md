# The seven thresholds behind the 2026-11-27 missed trade

On 2026-11-27 XAUUSD M15 ran from a 3562–3570 Asia range to ~3684 and the
indicator produced **no CORE signal**. Seven input thresholds are implicated.
This document records, for each one: the value it has now, the value its own
comment claims it replaced, where it is read, what it gates, and the exact
measurement that would tell us whether relaxing it was right.

> **Status: source-contract ready. No F7, no Strategy Tester, no bar replay has
> been run. Nothing in this file is a measurement.**

---

## 1. Provenance — read this before trusting the "was" column

The `was X` values are **comments in the source**, not a diff.

I tried to reproduce them from history and could not:

```
$ git log --format=%h -G"^input .*InpDisplacementATR" -- nadir2.mq5
8958330  2026-11-27   -> InpDisplacementATR = 0.9
3d332f7  2026-11-09   -> InpDisplacementATR = 0.9
8172522  2026-11-03   -> InpDisplacementATR = 0.9      <-- oldest commit containing nadir2.mq5
```

`nadir2.mq5` first appears in this repository at `8172522` (PR #28, 2026-11-03)
as a **44,207-line whole-file add**, and all seven inputs are *already* at their
current values in that first version. The `// was X` comments were written later,
at `3d332f7`. So:

- the "was" values describe a state of the indicator that **predates this
  repository's history** and cannot be checked out or diffed here;
- the change is **not** attributable to any commit in this repo. An earlier
  statement in this project's own review that the seven "entered at merge
  `fc633b8` (PR #76)" is **wrong** — `git log -G` does not support it;
- consequently **no before/after signal count exists, and none can be recovered
  from git.** It has to be produced fresh, in the Strategy Tester.

The practical consequence is good news: all seven are `input`s, so the A/B needs
**no code change at all** — only two `.set` files.

---

## 2. The table

`file:line` is `nadir2.mq5`. "Sites" counts non-comment reads of the input (or of
its shadow global).

| # | Input | Now | `was` (comment) | Declared | Sites | What it gates |
|---|---|---|---|---|---|---|
| 1 | `InpDisplacementATR` | **0.9** | 1.5 | `:839` | 14 in 7 functions | the displacement test itself — including whether a break is *labelled* MSS/BOS |
| 2 | `InpFVGMinSizeATR` | **0.2** | 0.3 | `:869` | 1 | minimum FVG height for an FVG to count as a causal zone |
| 3 | `InpRetestTimeoutBars` | **40** | 25 | `:1430` | 6 in 6 functions | how many bars a setup stays alive waiting for its retest |
| 4 | `InpRetestMaxDistanceATR` | **4.0** | 2.5 | `:1431` | 7 in 2 functions | how far price may travel into the zone and still count as a retest |
| 5 | `InpRequireMSSAfterSweep` | **false** | true | `:1508` | 6 in 5 functions | whether the structure anchor after a sweep must be an MSS specifically |
| 6 | `InpMaxStopATR` | **4.0** | 3.0 | `:1514` | 16 in 7 functions (via `g_cfgMaxStopATR`) | maximum stop distance; also reused by ZRE |
| 7 | `InpCausalDisplacementBodyATR` | **0.35** | 0.50 | `:1521` | 12 in 5 functions (via `g_cfgCausalDispBodyATR`) | minimum impulse-candle body for a causal OB/FVG binding |

### Where each one actually bites

**1. `InpDisplacementATR = 0.9`** — this is the one with the widest reach. It is
not only a leg filter; at `:25416` and `:25452` inside `DetectStructure()` it
decides the `displacement` flag on the break itself:

```
if(atr>0.0 && body>=atr*InpDisplacementATR) displacement=true;   // :25416 bullish, :25452 bearish
```

so lowering it changes **which breaks get the MSS/BOS label at all**, before any
gate is consulted. Other readers: `ValidateDisplacementLeg()` `:20286,:20293`,
`ValidateContinuationLeg()` `:17722,:17724,:17733,:17737`, `TopDown_Evaluate()`
`:17500,:17529,:17531`, `MergeSweepCandidates()` `:4085`, `SignalGateLegDiagLine()`
`:15781` (diagnostic text, not a gate), `OnInit` validation.

The refusal-log line this produces is the one to read in a replay:
`net 0.74/1.12 <REQ (InpDisplacementATR=0.90)` — a real example is in
`docs/demo_readiness_audit_v6.6.16.md`.

**2. `InpFVGMinSizeATR = 0.2`** — single site, `TryDetectFVGAt()` `:25828`:
`if(size<atr*InpFVGMinSizeATR) return false;`. Narrow and unambiguous.

**3. `InpRetestTimeoutBars = 40`** — `ManageSetupLifecycle()` `:23304`
(`age>InpRetestTimeoutBars` → `STATE_EXPIRED`), the expiry computation at
`:21750`, plus `PMI_BuildSequence()`, `QSMC_ApplyExecClassification()`,
`TacticalAuthorityDecide()`, `TacticalAuthorityGate()`.

**4. `InpRetestMaxDistanceATR = 4.0`** — `ManageSetupLifecycle()` `:23327-23328`:
`(zone_top - low[closed]) <= InpRetestMaxDistanceATR*atr` is one of the three
conditions for `retest=true`. `<=0` disables the test.

**5. `InpRequireMSSAfterSweep = false`** — two different effects:
- `ResolveCoreCausalPath()` / `SelectBestStructureAnchor()` `:18967,:18969` —
  with it `true`, only an MSS may anchor the path after a sweep;
- `CorePathTryBuild()` `:5494` — `(InpRequireMSSAfterSweep && st.type!=CE_MSS)`
  rejects a non-MSS anchor;
- `CorePathTryBuildContinuation()` `:5451` — the CONTINUATION path returns
  `false` immediately if it is `true`.

**This input is load-bearing for the v6.6.25 CONTINUATION feature.** Setting it
back to `true` silently kills every sweep-less chain **and produces no log line
saying so** — `:5451` returns before any `why` is set. That interaction is the
single most dangerous combination in this table and no gate currently asserts it.

**6. `InpMaxStopATR = 4.0`** — shadowed to `g_cfgMaxStopATR` at `:15295`,
auto-healed to `4.0` if `<=0` at `:15302`, name-validated at `:15357`. Consumed
by `CalculateAITradeSetup()`, `ScenarioEvaluateGeometry()`, `SigLog_FillZRE()`,
`ZRE_ParamsFromInputs()` and `EffMaxStopATR()` `:20368`:

```
double EffMaxStopATR()
   if(InpGateProfile!=QSMC_GATE_PRACTICAL) return g_cfgMaxStopATR;
   return MathMax(g_cfgMaxStopATR,6.0);          // practical ceiling: 6 ATR
```

so under `InpGateProfile=QSMC_GATE_PRACTICAL` the CORE path is really bounded by
**6.0 ATR**, not by this input — and ZRE reads `g_cfgMaxStopATR` directly. That
asymmetry is real and undocumented elsewhere.

**7. `InpCausalDisplacementBodyATR = 0.35`** — shadowed to
`g_cfgCausalDispBodyATR` at `:15297`, healed to `0.35` at `:15304`, validated at
`:15362`. Read by `ValidateDisplacementLeg()`, `ValidateCausalFVGAsOf()`,
`TryDetectFVGAt()` `:25833,:25834`, `MergeSweepCandidates()` `:4087`.

Note the relationship between #1 and #7: a leg needs a **net** move of
`0.9 × ATR` but only a **single body** of `0.35 × ATR`. The reversal leg asks
0.35 of body while the CONTINUATION leg asks 0.90 — that difference is recorded
in `docs/MISSED_TRADE_2026-11-27_HYPOTHESES.md`.

---

## 3. Can the "before" be replayed offline? **No.**

I checked, and the answer is no, for a concrete reason:

- there is **no OHLC bar data anywhere in this repository**. The only two CSVs
  are `docs/qsmc_smcvp_replay_xauusd_m15_2024_2025_signals.csv` (28 signal rows,
  2024–2025) and `docs/confirmation_replay_2026-11-25.csv` (9 rows) — both are
  *signal* dumps, not bar series, and neither covers 2026-11-27;
- the native harnesses (`tools/qats_sim/`, `tools/smcvp_sim/`,
  `tools/test_missed_trade_fixes_native.py`) compile real MQL5 bodies and drive
  them with **synthetic** scenarios. They can prove a predicate behaves as
  written; they cannot produce a signal count over a real week;
- a script that "counts signals" with no bars to count over would be a
  fabrication, so none is added.

What *is* possible offline is the attribution half, and it already exists: the
indicator writes a `[GateAudit]` refusal line and a SigLog CSV `gates` column
that name the failing key (`fail=leg_net`, `stop_atr<=4.00`, …). Once a tester
run produces those files, the counts per gate are a grouping exercise.

---

## 4. The measurement that would actually validate this

Everything below needs a terminal. It is the answer to "what must the owner do".

**Setup.** XAUUSD M15, the broker's own symbol suffix, tick data downloaded for
**2026-11-20 → 2026-11-28** (one week, so the 27th has context on both sides).
Indicator only — no EA — so nothing is traded and the count is not confounded by
execution refusals.

**Two runs, identical except the seven inputs.** All seven are `input`s, so this
is a `.set` change, not a code change. Keep every v6.6.25 switch **OFF** in both
runs so the only variable is the seven thresholds.

| input | Run A ("was") | Run B (shipped) |
|---|---|---|
| `InpDisplacementATR` | 1.5 | 0.9 |
| `InpFVGMinSizeATR` | 0.3 | 0.2 |
| `InpRetestTimeoutBars` | 25 | 40 |
| `InpRetestMaxDistanceATR` | 2.5 | 4.0 |
| `InpRequireMSSAfterSweep` | true | false |
| `InpMaxStopATR` | 3.0 | 4.0 |
| `InpCausalDisplacementBodyATR` | 0.50 | 0.35 |

**Record, per run:**

1. total CORE signals in the window, and the timestamp of each;
2. whether any CORE signal falls on **2026-11-27 between the Asia range and the
   ~3684 high** — the specific leg this table exists for;
3. the full `[GateAudit]` refusal histogram (count per `fail=` key);
4. the SigLog CSV, so the `gates` column can be diffed.

**Then, one input at a time.** Seven more runs, each starting from Run A and
changing exactly one input to its shipped value. That is what separates "these
seven together were needed" from "one of them did all the work and the other six
are unmeasured risk". Without the one-at-a-time pass, a relaxation that only
ever fires on this one week looks identical to a general improvement.

**The overfitting test.** A change is a fix if it generalises to a
market-structure class; it is a fit if it only ever catches the 2026-11-27 leg.
So repeat the whole A/B on at least one **other** window with a comparable
vertical leg, and require that the shipped values do not merely add signals but
add them where the refusal histogram says the gate was the binding constraint.

**What "validated" would mean.** Not "more signals". A relaxation that doubles
the signal count and halves the average RR1 is worse. The acceptance evidence is:
the 2026-11-27 leg appears, the refusal histogram moves on the keys this table
names, and the added signals survive the entry review rather than being refused
downstream.

---

## 5. Known interactions and gaps

| | |
|---|---|
| `InpRequireMSSAfterSweep=true` silently disables CONTINUATION | `:5451` returns before setting `why`. No log line. **No gate asserts this.** |
| `InpMaxStopATR` is not the CORE ceiling under `QSMC_GATE_PRACTICAL` | `EffMaxStopATR()` `:20368` raises it to 6.0; ZRE still reads the raw value |
| `InpDisplacementATR` changes the MSS/BOS label, not just a filter | `:25416`, `:25452` inside `DetectStructure()` |
| `0` disables, it does not mean "zero" | `InpRetestMaxDistanceATR<=0` skips the distance test; `g_cfgMaxStopATR<=0` is auto-healed to 4.0 |
| The gate profile banner is the only place a relaxation is announced | `PrintGateProfileBanner()` — *"a relaxation the operator cannot read is a silent one"* |

`docs/SIGNAL_VISIBILITY_DIAGNOSIS.md` records what each of the seven is
load-bearing for. It does not contain a measurement, because none exists.

---

## 6. Cross-references

- Root-cause hypotheses: [`MISSED_TRADE_2026-11-27_HYPOTHESES.md`](MISSED_TRADE_2026-11-27_HYPOTHESES.md)
- What each threshold is load-bearing for: [`SIGNAL_VISIBILITY_DIAGNOSIS.md`](SIGNAL_VISIBILITY_DIAGNOSIS.md)
- F7 and Tester procedure: [`QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md`](QSMC_V6.6.25_F7_AND_TESTER_HANDOFF.md)
- Buffer contract the run must be read through: [`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md)
- Gate that keeps this table honest: `tools/test_seven_thresholds.py`
