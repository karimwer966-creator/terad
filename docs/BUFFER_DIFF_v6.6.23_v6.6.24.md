# Buffer 7..12 replay diff — v6.6.23 vs v6.6.24

**What this document is.** A procedure, and the list of differences that are
*expected* to appear when the two builds are dumped on the same history. It is
not a test result: nothing in this repository can run the indicator, so the dump
has to be produced inside MetaTrader 5 by the owner.

**What it is not.** Not a Compile, not a backtest, not a performance claim. No
file in this repository has been compiled by MetaEditor: the host has no MQL5
compiler, and `F7` remains the only judge.

---

## 1. Why a dump at all

The executor trusts eleven numbers published by the indicator:

| Buffer | Slot | Meaning |
|---|---|---|
| 7 | `QSMC_BUF_CORE_DIR` | +1 buy, -1 sell, 0 no signal |
| 8 | `QSMC_BUF_CORE_ENTRY` | planned entry |
| 9 | `QSMC_BUF_CORE_SL` | stop |
| 10 / 11 / 12 | `QSMC_BUF_CORE_TP1/2/3` | targets |
| 21..25 | class, score, reliability, rr1, risk multiplier | the executor's profile |

A release that says "the signal path is unchanged" is making a claim about an
*output*. The only way to check an output claim is to compare outputs. The EA's
own journal cannot do it: by the time the EA sees the buffers, the refusal and
the sizing logic have already thrown the evidence away.

`MQL5/Scripts/QSMC_BufferDump.mq5` (R4) dumps all eleven slots for the last
`InpBars` bars into `QSMC_buffers.csv` in the terminal's data folder, one row per bar, with the
copy counts and `BarsCalculated` on every row so a partial copy is visible
instead of looking like a zero.

## 2. The procedure

```
1. Copy the whole repository at each tag you want to compare into two folders.
2. Terminal A: compile nadir2.mq5 from the v6.6.23 tree, attach it to
   XAUUSD M15, let it calculate ~300 bars.
   Run QSMC_BufferDump.mq5 (InpBars=200, InpOutFile=QSMC_buffers_v6623.csv).
3. Terminal B (or the same terminal after removing nadir2.ex5): the v6.6.24
   tree, identical steps, QSMC_buffers_v6624.csv.
4. diff -u QSMC_buffers_v6623.csv QSMC_buffers_v6624.csv
```

Rules for a diff that means something:

* same **symbol**, same **timeframe**, same **bar count**, same **broker
  history**. A different feed invalidates everything below.
* the indicator must be read with its **compiled defaults** in both cases — the
  EA and the dump script both pass no input list.
* compare the **closed** bars only (every row whose time is not the current
  bar). The forming bar is allowed to differ between two runs.

## 3. What MUST be identical

* the `bar_time` column, row for row, and `period_minutes`;
* `copied_*` counts: all eleven must read `200` in both dumps;
* every row where `core_dir = 0` — a bar with no signal in the old build must
  not carry an entry, stop or target in the new one;
* the **geometry relations** on every bar that has a signal in both builds:
  `core_sl` on the risk side of `core_entry`, `core_tp1 < core_tp2 < core_tp3`
  for a buy and reversed for a sell, and the same ordering in both dumps;
* the **class integer** for bars that both builds classify (21..25 were not
  touched by v6.6.24).

## 4. What MAY differ, and exactly why

v6.6.24 carries **two Class B changes to the evidence model**, each in its own
commit, marked `[needs owner approval]`. If either is merged, buffers 7..12 can
legitimately differ:

| Finding | Commit | Effect on the buffers |
|---|---|---|
| **F-008** piercing / dark cloud restored | `[needs owner approval] F-008` | two of the four named reversal patterns could never fire (`r_c` had to be above *and* below the same price). With the fix, E2 (candle evidence) can be earned by those shapes, so `evidence_count` can rise by one, the reaction score by up to 10 points, and a candidate that used to fail `min_evidence`/`min_score` can now appear in buffer 7. |
| **F-009** missing volume baseline no longer counts as evidence | `[needs owner approval] F-009` | on a symbol whose volume history is unusable, a bar used to earn `QEV_VOLUME` for free. It no longer does: `evidence_count` can fall by one and a candidate can disappear from buffer 7. |

Consequences for reading the diff:

* **more `core_dir != 0` rows** than v6.6.23 → consistent with F-008;
* **fewer** `core_dir != 0` rows → consistent with F-009;
* a bar that flips **direction** between builds is consistent with *neither* and
  must be investigated before the trial starts;
* a bar whose `core_sl`/`core_tp*` moves while `core_dir` is unchanged is
  consistent with *neither* — geometry is not what the two Class B changes
  touch, so that would be a defect in this release.

If **both** Class B commits are dropped, the expected diff is empty on the
closed bars. That is the cleanest outcome to start a trial from, and it is the
owner's call.

## 5. Pasting the result into the trial record

Save the three files next to the trial record:

```
docs/incident-…/evidence/QSMC_buffers_v6623.csv
docs/incident-…/evidence/QSMC_buffers_v6624.csv
docs/incident-…/evidence/buffer-diff.txt
```

`QSMC_trial_<login>.csv` (R1) is the *execution* record; the buffer diff is the
*signal* record. The trial report is only honest with both.
