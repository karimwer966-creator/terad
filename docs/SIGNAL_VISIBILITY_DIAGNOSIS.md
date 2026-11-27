# Signal visibility — the seven relaxed thresholds, what each one actually gates

Seven `input` declarations in `nadir2.mq5` carry a `// was X` comment pointing at
this file. Until now the file did not exist, so the seven comments cited nothing.
This is that file: for each threshold, the value that ships, the value the comment
says it replaced, and **every** decision in the code that reads it — because most
of them gate more than one thing, and relaxing one number moved several decisions
at once.

**What this document is not.** It is not a backtest, not a MetaEditor compile and
not evidence that any of these values is profitable. No signal count before/after
was ever measured here: this repository has no MetaEditor and no Strategy Tester.
What follows is a code map plus the audit evidence that already exists in
`docs/`, with its limits stated.

## 1. Provenance of the "was" values

The `// was X` numbers come from the code comments themselves, and they are the
only record in this checkout: the deepest commit available here (`fc633b8`, the
merge that opened this history) **already** carries all seven current values, so
no diff of the change can be reproduced from git. Treat "was" as a comment claim,
not as a verified previous state.

The relaxation is older than the v6.6.15/v6.6.16 audit cycle:
`docs/audit_v6.6.15_RCA.md` and `docs/demo_readiness_audit_v6.6.16.md` both already
report `InpDisplacementATR=0.90` and `g_cfgCausalDispBodyATR=0.35` as the shipping
values. Those audits are therefore evidence about the **current** thresholds, not
evidence that relaxing them produced more signals — and their finding is the
opposite of a clean win: with 0.90/0.35 in place, the 2026-11-05 XAUUSD M15
candidates were still refused
(`net 0.74/1.12 < REQ`, `best_body 0.28 ATR` against a 0.35 requirement).

## 2. The seven thresholds

All line numbers are in `nadir2.mq5` at the commit this file was written against
(`aa09275`), CRLF file.

| # | Input | Ships | Comment says | Declared |
|---|---|---|---|---|
| 1 | `InpDisplacementATR` | 0.9 | was 1.5 | L839 |
| 2 | `InpFVGMinSizeATR` | 0.2 | was 0.3 | L869 |
| 3 | `InpRetestTimeoutBars` | 40 | was 25 | L1430 |
| 4 | `InpRetestMaxDistanceATR` | 4.0 | was 2.5 | L1431 |
| 5 | `InpRequireMSSAfterSweep` | false | was true | L1508 |
| 6 | `InpMaxStopATR` | 4.0 | was 3.0 | L1514 |
| 7 | `InpCausalDisplacementBodyATR` | 0.35 | was 0.50 | L1521 |

Six of the seven are monotone relaxations (a smaller floor, a wider window, a
wider stop). #5 removes a requirement outright: `false` means a sweep no longer
has to be followed by an MSS break to become an anchor.

## 3. What each one gates

### 3.1 `InpDisplacementATR` = 0.9 — five decision sites in four functions

The comment says "MSS label + leg net", and that is still an understatement.
Every reader of this input:

| Decision | Function | Line | Effect |
|---|---|---|---|
| the **MSS/BOS label itself** | `DetectStructure()` | L25416, L25452 | `if(atr>0.0 && body>=atr*InpDisplacementATR) displacement=true;` — a break is only *labelled* displacement-backed when a candle body clears 0.9 × ATR |
| reversal leg net | `ValidateDisplacementLeg()` | L17529 | `net<atr*InpDisplacementATR` → `LegNoteFail("leg: net sweep->break move < InpDisplacementATR")` |
| reversal leg audit row | `ValidateDisplacementLeg()` | L17500 | publishes `g_gate_audit.leg_required_net` |
| **v6.6.25 C** continuation leg | `ValidateContinuationLeg()` | L17722, L17733 | net move *and* the impulse body must clear 0.9 × ATR; refusal strings `"continuation: net leg move < InpDisplacementATR x ATR"` / `"continuation: no impulse candle with body >= InpDisplacementATR x ATR before the BOS"` |
| M15 top-down sequence | `TopDown_Evaluate()` → `TopDown_Sequence15` | L35646 | the M15 sequence term of the top-down verdict uses the same multiple |

Diagnostics that print it: `OnInit()` L15781 (`- Displacement ATR:`) and
`SignalGateLegDiagLine()` L20286/L20293.

Consequence worth knowing before touching it: because the **label** and the
**gate** share one number, lowering it makes more breaks displacement-backed *and*
lets more legs through. It is not possible to relax one without the other while
they share the input.

### 3.2 `InpFVGMinSizeATR` = 0.2

One reader: `TryDetectFVGAt()` L25828 —
`if(size<atr*InpFVGMinSizeATR) return false;`. A gap smaller than 0.2 × ATR is not
registered as an FVG at all, so it cannot serve as the causal zone for a setup.
Lowering it admits smaller gaps as evidence.

### 3.3 `InpRetestTimeoutBars` = 40

| Decision | Function | Line | Effect |
|---|---|---|---|
| setup retirement | `ManageSetupLifecycle()` | L23304 | `if(InpRetestTimeoutBars>0 && age>InpRetestTimeoutBars)` — an armed setup older than 40 closed bars is retired |
| execution classification | `QSMC_ApplyExecClassification()` | L21750 | the same window decides whether a confirmed setup still counts as executable |
| tactical authority | `TacticalAuthorityGate()` passes it | L32854 | `TacticalAuthorityDecide(bull,src,age,InpRetestTimeoutBars,…)` — the authority window is this input, and the refusal text at L32805 names it |
| PMI sequence lookback | `PMI_BuildSequence()` | L11438 | `int lookback=PMI_IMax(1,InpRetestTimeoutBars);` |

Raising 25 → 40 keeps a setup alive 60 % longer, and — through the PMI reader —
also widens an unrelated sequence window. The order-block retest registry follows
the same convention by comment (L19123, L19131), not by reading the input.

### 3.4 `InpRetestMaxDistanceATR` = 4.0

One decision, evaluated per side inside `ManageSetupLifecycle()`: L23327 for a
setup owned from above (`(g_active_setup.zone_top-l[closed])<=InpRetestMaxDistanceATR*atr`)
and L23336 for one owned from below (`(h[closed]-g_active_setup.zone_bottom)<=…`) —
how far price may travel from the zone and still count as retesting it. `<=0`
disables the check. Also validated in `OnInit` (`InpRetestMaxDistanceATR<0.0` is
refused by name, L15318/L15365) and printed there (L15795).

### 3.5 `InpRequireMSSAfterSweep` = false

| Decision | Function | Line | Effect while `true` |
|---|---|---|---|
| anchor selection | `SelectBestStructureAnchor()` | L18967 | `if(InpRequireMSSAfterSweep && st.type!="MSS")` → `GateAuditReject("anchor: <type> break rejected (InpRequireMSSAfterSweep)")` |
| core path build | `CorePathTryBuild()` | L5494 | a non-MSS structure cannot start a core path |
| core path resolve | `ResolveCoreCausalPath()` | L5604 | non-MSS candidates are skipped |
| **v6.6.25 C path switch** | `CorePathTryBuildContinuation()` | L5451 | the guard is `… || InpRequireMSSAfterSweep || …` → `return false`, so **setting this back to `true` disables the CONTINUATION chain entirely**, not just the reversal anchors |

The comment calls this "the top blocker", and the code agrees about the mechanism:
with `true`, every BOS-type break is refused at the anchor stage before geometry or
RR is ever considered. `docs/QSMC_CORE_ZERO_INVESTIGATION.md` records the same fact
from the other direction ("`InpRequireMSSAfterSweep` defaults false, so this is not
an unconditional MSS-only rule").

The L5451 row is the one to remember before touching this input again: it is the
only place where a pre-v6.6.25 threshold silently gates a v6.6.25 switch. Turning
the MSS rule back on while `InpAllowContinuationChain=true` produces no
`[CONTINUATION]` lines at all, and nothing in the log says why.

### 3.6 `InpMaxStopATR` = 4.0

Read through the shadow `g_cfgMaxStopATR` (L2064, assigned L15295, healed to 4.0 at
L15302, refused when `<=0` at L15316/L15357):

| Decision | Function | Line | Effect |
|---|---|---|---|
| geometry gate | `CalculateAITradeSetup()` | L22559, L22565 | `risk>atr*EffMaxStopATR()` → `GateAuditReject("geometry: stop distance above g_cfgMaxStopATR")`; the funnel row is `STOP_TOO_WIDE` (codes listed at L20908, L20913, L21037) |
| effective ceiling | `EffMaxStopATR()` | L20368–L20371 | returns `g_cfgMaxStopATR`, except under `QSMC_GATE_PRACTICAL`, where the ceiling becomes `max(g_cfgMaxStopATR, 6.0)` |
| CORE journal gate row | `SigLog_AddCore()` | L14908 | `stop_atr<=<EffMaxStopATR()>` column |
| **ZRE** stop gate | `ZRE_ParamsFromInputs()` → `ZRE_ComputeEntrySL()` | L39297, L38297 | `p.max_stop_atr=MathMax(0.1,g_cfgMaxStopATR)` and the refusal `why="STOP %.1f ATR > %.1f"` — the ZRE entry stop is measured against the same number |
| **ZRE** journal gate row | `SigLog_FillZRE()` | L14957 | `stop_atr<=<g_cfgMaxStopATR>` — the ZRE rows report against the raw shadow, **not** `EffMaxStopATR()` |

So the comment's "also reused by ZRE" is true twice over, and it exposes the one
asymmetry in this table: `EffMaxStopATR()` is what the CORE geometry gate and the
CORE journal row read, so under `QSMC_GATE_PRACTICAL` they move to 6 ATR, while the
ZRE stop gate and the ZRE journal row keep measuring against the raw 4. The
ZRE-internal default (`ZRE_ParamsInit()` L37925, `3.0`) is overwritten from the
input, and `ZRE_SelfTestReaction()` L38889 uses `1.0` — self-test only, not live.

### 3.7 `InpCausalDisplacementBodyATR` = 0.35

Read through the shadow `g_cfgCausalDispBodyATR` (L2066, assigned L15297, healed to
0.35 at L15304, refused when `<=0` at L15317/L15362):

| Decision | Function | Line | Effect |
|---|---|---|---|
| impulse candle inside the reversal leg | `ValidateDisplacementLeg()` | L17549, L17557 | the leg needs one candle whose body/ATR `>= 0.35`; otherwise `LegNoteFail("leg: no separate impulse candle >= g_cfgCausalDispBodyATR")` |
| FVG as causal evidence | `ValidateCausalFVGAsOf()` | L17642 | the FVG's forming candle body must clear 0.35 × ATR |
| FVG detection | `TryDetectFVGAt()` | L25833 | same body floor at detection time |
| audit row | `ValidateDisplacementLeg()` | L17502 | publishes `g_gate_audit.leg_required_body` |

This is the threshold behind the `LEG_GEOMETRY` refusals in
`docs/audit_v6.6.15_RCA.md` (verdict code 19, "the impulsive candle's real body was
less than 0.35 ATR long"), and note the asymmetry the v6.6.25 C path relies on: the
**reversal** leg asks 0.35 × ATR of body, while the **continuation** leg asks the
full `InpDisplacementATR` = 0.90 (see 3.1).

## 4. What is still unproven

1. **No before/after measurement.** Nobody has counted CORE signals with the old
   values versus the new ones. The direction of the risk is knowable from the code
   (six relaxations plus one removed requirement ⇒ more candidates reach the gates),
   the size of it is not.
2. **The audits that exist do not validate the relaxation.** `demo_readiness_audit_v6.6.16.md`
   explicitly kept these values unchanged and still observed refusals; it is a
   diagnostic-quality report, not a tuning study.
3. **No F7.** Nothing in this file was compiled or run in a terminal.
4. **`// was` is a comment.** If the seven previous values matter to a decision,
   they need a source outside this checkout.

## 5. How to see the effect yourself

Every gate above names its own failing predicate, so the effect is observable
without changing code:

- `[GateAudit]` / `GateAuditReject(...)` lines carry the exact reason
  (`"anchor: BOS break rejected (InpRequireMSSAfterSweep)"`,
  `"geometry: stop distance above g_cfgMaxStopATR"`, …).
- `SignalGateLegDiagLine()` (L20279) prints the measured numbers against the
  requirement in the form
  `net <measured>/<required> OK|<REQ (InpDisplacementATR=0.90) | best_body 0.28ATR (need >= 0.35)`,
  e.g. the real line in `docs/demo_readiness_audit_v6.6.16.md` reads
  `net 0.74/1.12 <REQ (InpDisplacementATR=0.90) | best_body 0.28ATR (need >= 0.35)`.

- `OnInit` prints the effective values of all seven (`- Displacement ATR:`,
  `- RetestTimeout: … bars / … ATR`, `- Mandatory: MSS=…`) at L15781–L15797.
- the SigLog CSV carries the `stop_atr<=…` gate row for CORE (L14908) and ZRE
  (L14957) records.
- `tools/why_no_trades.py` reads those rows offline.

A tuning study would be: fix one symbol/timeframe and history, run each threshold
at old and new value with everything else identical, and compare CORE publications
per week plus the funnel row that refused the rest. That has not been done.
