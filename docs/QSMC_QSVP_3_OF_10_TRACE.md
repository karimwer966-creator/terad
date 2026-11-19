# Source trace: "[QSVP] … SELL candidate 3/10, FAIL at LIQUIDITY SWEEP"

Question: what do the numerator (3) and denominator (10) mean, with
file:line evidence, and what this message is NOT.

## 1. Denominator — `SVP_MAX_STEPS = 10`

- `MQL5/Include/QSMC/QSMC_SvpCore.mqh:22` — `#define SVP_MAX_STEPS 10`.
- Step indexes and names:
  - `MQL5/Include/QSMC/QSMC_SvpDecision.mqh:36-45` — 0=H4, 1=H1,
    2=M15 LIQUIDITY, 3=LIQUIDITY SWEEP, 4=DISPLACEMENT, 5=BOS/CHoCH,
    6=OB/FVG, 7=VOLUME PROFILE, 8=ENTRY, 9=RISK/REWARD.
  - `QSMC_SvpDecision.mqh:135-148` (`SVP_StepName`) maps the same indexes to
    display strings: 0 "H4 BIAS", 1 "H1 STRUCTURE", 2 "M15 LIQUIDITY",
    3 "LIQUIDITY SWEEP", 4 "DISPLACEMENT", 5 "BOS/CHoCH", 6 "OB/FVG",
    7 "VOLUME PROFILE", 8 "ENTRY", 9 "RISK/REWARD".
- It is a fixed count of sequential gate steps, NOT a maximum score, NOT
  points, NOT weighting.

## 2. How each step gets PASS / FAIL / PENDING / NA

- `QSMC_SvpDecision.mqh:187-192` (`SVP_SetStep`) — writes status and text per
  step.
- Example (the sweep step itself, `QSMC_SvpDecision.mqh:296-322`): the sell side
  needs a buy-side liquidity sweep (`need=-d`); it picks the newest still-young
  matching sweep (`SVP_PickSweep`, ~207–217). If none qualifies, LIQUIDITY may
  already be PASS while SWEEP is set to `PENDING` ("not swept yet", line 307) or
  `FAIL` (line 322). `SVP_SweepActionable` governs PASS vs PENDING vs FAIL.

## 3. Numerator — `progress`

`QSMC_SvpDecision.mqh:501-507`:

```
s.progress=0; s.blocking=-1;
for(int i=0;i<SVP_MAX_STEPS;i++)
{
   if(s.status[i]==SVP_STEP_PASS) { if(s.blocking<0) s.progress++; }
   else if(s.blocking<0) s.blocking=i;
}
```

So `progress` = the number of **leading, consecutive PASS steps** starting at
step 0 before the first non-PASS step; `blocking` = the index of that first
non-PASS step. Steps after the blocker are ignored for the numerator.

For "SELL candidate 3/10, FAIL at LIQUIDITY SWEEP":

- SELL side (`focus = -1`) was being reported (tie-break logic
  `QSMC_SvpDecision.mqh:593-606`: the side with the larger `progress` is the
  focus side when neither qualifies).
- Steps 0 (H4 BIAS), 1 (H1 STRUCTURE), 2 (M15 LIQUIDITY) were PASS → progress=3.
- Step 3 (LIQUIDITY SWEEP) was the first non-PASS, and its status was FAIL
  (not PENDING/NA) → `blocking=3`.
- Therefore "3/10" = "three gate steps passed, then the fourth gate failed".
- Steps 4–9 are irrelevant to the numerator once step 3 failed.

## 4. Where the message text is composed and printed

- `QSMC_SvpDecision.mqh:615-619` —
  `g_svp.reason = "WAIT - "+(focus>0?"BUY":"SELL")+" candidate "+progress+"/"+SVP_MAX_STEPS+", "+SVP_StatusText(g_svp.status[blk])+" at "+SVP_StepName(blk)+": "+g_svp.text[blk]`
- `SVP_StatusText` maps `SVP_STEP_FAIL` → `"FAIL"` (`QSMC_SvpDecision.mqh:150-156`).
- The `[QSVP]` line in the journal is printed by the QSVP display engine:
  `MQL5/Indicators/QSMC_SmcVpEngine.mq5:362`
  (`Print("[QSVP] ",TimeToString(g_svp.bar_time,...)," ",line)`, with `InpSveLog`
  at `QSMC_SmcVpEngine.mq5:148` and `g_svp.reason` copied at ~355–362).
- If the same engine is attached in nadir2/EA contexts is a separate wiring
  question; the literal tag seen in the log (`[QSVP]`) is this engine's.

## 5. What this message is NOT

- NOT a CORE score (CORE's score buffer is buffer 21 / `BufSigCoreScore` in
  nadir2; different engine, different meaning: 0–100 evidence quality).
- NOT an executable signal: `SVP_Resolve` (`QSMC_SvpDecision.mqh:512-517`)
  returns BUY/SELL only when **all ten** steps PASS and the plan is valid;
  this message comes from the `WAIT … candidate` branch (`:609-620`), i.e. the
  side does not qualify. Any execution still depends on the EA's own CORE
  arbiter/gates, not on QSVP.
- NOT evidence of a missed trade or of profitability — it is a diagnostic of
  where the QSVP sequence stopped.
- NOT comparable as "3 out of 10 = 30% confidence". It is ordinal, sequential,
  and capped by the first blocker.

## 6. How to use it

Legitimate uses: log that SELL-side H4/H1/M15-liquidity stages were satisfied
and the liquidity-sweep confirmation was absent at that bar; correlate with
CORE buffers 7–25 via the fixed-range dump or a Tester replay. Illegitimate
uses: position sizing, entry triggers, "confidence %" displays, or counting
the candidate as an EA signal. Do not infer CORE behavior from this line alone.
