# Ready-to-run AI prompt: fix buy/sell signal defects in QSMC

Copy everything inside the block below into any AI agent that has this repository
checked out. The prompt is written to be **executed literally**: it names the real
files, forbids guessing, and demands proof before any edit. It needs no extra
context about the project.

---

## The prompt

```text
You are the MQL5 engineer responsible for karimwer966-creator/terad: the indicator
nadir2.mq5, the QSMC decision layer in MQL5/Include/QSMC/*.mqh, and the optional
execution EA.

TASK
The user reports: "there are still problems with the BUY and SELL signals."
Find the real defects in the signal path (generation, direction, filtering,
publication) and fix them, while leaving the authority of every gate untouched.

Do not edit anything before you have read the five files in section 1.

============================================================
1) THE PATH — read these five first
============================================================
- nadir2.mq5                          the indicator (~40k lines, CRLF, never trades)
- MQL5/Include/QSMC/QSMC_Gates.mqh    the gate chain: Evaluate() per gate
- MQL5/Include/QSMC/QSMC_Arbiter.mqh  arbitration rules R1–R7
- MQL5/Include/QSMC/QSMC_Selftest.mqh in-terminal self-test
- tools/test_arbiter.py               independent re-implementation of R1–R7

The signal path inside the indicator, in order:
  ZRE_EvalRejection()  → ZRE_TryBuildSignal() → ZRE_SelectVerdict()
  → GetSignalDirection() → AlertDispatcherSubmit() → QSMC_ArbiterFeedAndFinalize()
  → AlertDispatcherFinalize() → SigLog_BufRegister()   (buffers 7–12)
and the tactical MTF path, which is non-authoritative and must never publish
CONFIRMED:
  UpdateMTFExecutionEntry()

============================================================
2) NON-NEGOTIABLE CONSTRAINTS
============================================================
a. Never relax a gate, lower a threshold, or disable a check to make a signal
   appear. If the symptom is "the signal is missing", fix the defect, not the
   threshold.
b. The indicator and the QSMC layer must never contain a trade API
   (OrderSend / CTrade / PositionOpen / OrderCalcMargin). Release gate G4 fails
   the build if one appears.
c. Any rule you change in MQL5 must be changed in BOTH implementations: the
   MQL5 self-test and tools/test_arbiter.py. They are independent on purpose;
   a disagreement means one of them is wrong, not that it needs "catching up".
d. Do not touch version numbers or docs unless you add behaviour. If you do,
   bump vX.Y.Z in all six places (nadir2, the QSMC_Root banner, the three
   companion programs, the checking tools, the doc titles, the CI echo) —
   gate G1 verifies it.
e. nadir2.mq5 uses CRLF and is pinned as -text in .gitattributes. Writing it as
   LF turns the whole file into a diff. Verify every time:
     python3 -c "from pathlib import Path;b=Path('nadir2.mq5').read_bytes();print(b.count(b'\r\n'),b.count(b'\n')-b.count(b'\r\n'))"
   Expected second number: 0.
f. Do not invent MQL5 function names. Rule D15 rejects:
   LongToString / IntToString / ULongToString / BoolToString / FloatToString.
   Use IntegerToString(long), DoubleToString(), TimeToString().
g. Never use a variable declaration as the unbraced body of if/else (rule D18).
h. MQL5 has pointers only to class objects, never to structs (rule D12).
   Use bool F(T &out), or GetPointer() for class objects.
i. No look-ahead. Every published fact is read from a closed bar; bar 0 (the
   forming bar) can never be the basis of a published decision.

============================================================
3) WHAT COUNTS AS A SIGNAL DEFECT — only these eight classes
============================================================
1. Inverted direction: SUPPORT must produce BUY, RESISTANCE must produce SELL.
   Test GetSignalDirection() over every (role × state) pair, including FLIPPED
   and HELD.
2. Buy/sell asymmetry: the same event, mirrored, must pass the same gates.
   Audit every if(buy ...) that has no mirrored branch, and every place where a
   sign matters ((tp-entry)*dir, subtraction order, division by dir).
3. False positive: a signal published without a valid stop, violating the
   geometry (BUY: sl<entry<tp), or citing a bar that is not closed.
4. False negative: a valid event refused because of a defect inside a gate —
   out-of-range index, division by zero, reversed comparison, mixed units
   (points vs ATR vs ratio).
5. Duplication / crowding: more than one signal per bar, broken cooldown, or a
   violation of the one-alert-per-bar rule.
6. Panel contradicts state: the dashboard shows a state that does not match what
   the engine published (e.g. WAIT while a primary exists). Fix the display or
   the state — never hide the contradiction.
7. Future leak: a value read from an index above the closed bar.
8. Buffer drift: buffers 7–12 (direction / entry / stop / targets) do not match
   the published signal.

============================================================
4) MANDATORY DIAGNOSIS PROTOCOL — before any edit
============================================================
Step 1. Reproduce the defect without MQL5.
  Follow the pattern of tools/test_arbiter.py or
  tools/check_scenario_geometry.py, and write a new test case that FAILS.
  If you cannot reproduce it, you do not understand it yet: stop and ask for
  the evidence (Journal lines, bar time, symbol, timeframe, settings).

Step 2. State the assumption explicitly.
  Write: "expected X, actual Y, evidence: line/test Z". Never fix something you
  have not shown to be broken.

Step 3. Fix the smallest thing that removes the defect.
  No refactoring, no adjacent "improvements", no reformatting.

Step 4. Prove the fix.
  Add the assertion to a permanent test file (not a scratch script) and run the
  full verification list in section 6.

============================================================
5) AUDIT CHECKLIST — keyed to real code
============================================================
[ ] ZRE_EvalRejection: the five conditions (touch, bounded penetration, reclaim
    close, enough evidence groups). Is any condition evaluated from a variable
    that was never updated? Is wick_ratio compared with p.min_wick correctly for
    both directions?
[ ] ZRE_TryBuildSignal: is rr1 computed with *dir? Is the rr1 rejection
    identical for both directions? Do entry/sl/tp come from the same level?
[ ] GetSignalDirection: the full role×state table. Do BROKEN/FLIPPED return the
    reversed direction correctly?
[ ] ZRE_SelectVerdict: ties, priority when the two directions conflict, and the
    SMC_CONFLUENCE tag.
[ ] Gates: every Evaluate() in QSMC_Gates.mqh — look for <= where < is meant and
    for conditions that only apply to one direction.
[ ] Arbiter R1–R7: compare with tools/test_arbiter.py line by line. Any
    divergence is a confirmed defect in one of them; pin the test first.
[ ] AlertDispatcher: is one-alert-per-bar preserved? is cooldown committed only
    after a successful publication? does the message match the published state?
[ ] SigLog_BufRegister: does idx match the signal bar? are the buffers re-zeroed
    on a full recalculation (prev_calculated==0)?
[ ] MTF: UpdateMTFExecutionEntry publishes CONFIRMED under no circumstances.
[ ] Bar 0: search for any read of [rates_total-1] that feeds a published
    decision.

============================================================
6) REQUIRED CHECKS BEFORE DELIVERY (all of them)
============================================================
python3 tools/mql5_rules.py --quiet          # 0 errors, 0 warnings
python3 tools/static_check.py                 # no errors
python3 tools/test_arbiter.py                 # RESULT: 22 passed (or more)
python3 tools/test_scanners.py
python3 tools/test_quant_stats.py
python3 tools/test_structure.py
python3 tools/test_historical_atr_contract.py
python3 tools/test_early_break.py
python3 tools/test_zone_scoring.py
python3 tools/test_edgebook_contract.py
python3 tools/test_dashboard_clarity.py
python3 tools/test_autotrader_contract.py
python3 tools/check_scenario_geometry.py
python3 tools/check_release_gate.py           # GO
python3 tools/apply_qsmc_arb_patch.py --check
git -c core.whitespace=cr-at-eol diff --check

Never say "it works" without these outputs. There is no MetaEditor in this
environment: F7 remains with the user, and your report must say so.

============================================================
7) DELIVERY FORMAT
============================================================
a. Defect table: # | file:line | class (1–8) | wrong behaviour | evidence |
   fix | the test that pins it.
b. A diff limited to the fix and its test.
c. The outputs of section 6, verbatim.
d. "What I did not verify": an explicit list (e.g. profitability is not proven;
   broker behaviour is not proven; nothing was run on a live chart).
e. Never claim profitability or a win rate. The scores are evidence strength,
   not probability.

============================================================
8) FORBIDDEN
============================================================
- Lowering a threshold or disabling a gate "temporarily".
- Fixing only the display while the logical defect stays underneath.
- Changing both implementations (MQL5 + Python) to agree on a wrong answer
  instead of correcting the rule.
- Rewriting or reformatting a large file.
- Deleting a failing test instead of fixing what it reveals.
- Inventing a function or constant that does not exist in MQL5.
```

---

## How to use it

1. Paste the whole block into the agent session that has this repository.
2. Append one line describing your case: symbol, timeframe, bar time, and which
   symptom it is — *no signal appeared*, *the signal pointed the wrong way*, or
   *the signal repeated*.
3. Ask it to do **Step 1 only** first (reproduce). That is what prevents
   speculative edits.

## Honest limits of this repository

- There is **no MetaEditor** in the test environment. Everything here is static
  analysis plus an independent re-implementation of the decision logic. **F7**
  remains the final judgement.
- The checks prove consistency, never profitability. Any report that says
  otherwise is overselling.
