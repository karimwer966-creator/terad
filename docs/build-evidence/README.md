# Build evidence — MetaEditor F7

Everything under `tools/` proves source invariants. **None of it is a compile.** This
folder is where the platform evidence lives: the actual MetaEditor output, pasted
verbatim, one file per program per attempt.

The rule is simple and deliberately hostile to optimism: **a program counts as
"compiled" only if a log in this folder says `0 errors` for it.** No source contract,
no green CI run and no summary in prose can move a row in the table below.

## F7 matrix

| Program | Role | F7 | Errors | Evidence |
| --- | --- | --- | --- | --- |
| `MQL5/Indicators/QSMC_ScannerProbe.mq5` | scanner table (observation only) | **PASS** | 0 errors, 0 warnings | `2026-11-02_QSMC_ScannerProbe_F7.log` |
| `MQL5/Experts/QSMC_AutoTrader.mq5` | the ONLY file that can trade; carries the 100/200/300 pip ladder | **PASS** | 0 errors, 0 warnings | `2026-11-02_QSMC_AutoTrader_F7.log` |
| `nadir2.mq5` | the 43k-line signal host + decision card | **PENDING** | — | — |
| `MQL5/Experts/KLJ_DataFeeder.mq5` | optional out-of-process data feed | **PENDING** | — | — |

The two PASS rows are ordered by risk, not by date: the trading companion had to
compile first because it is the only file that can lose money, and because it is the
file that now carries the fixed-lot / pip-ladder code. **`nadir2.mq5` is still the
largest unknown**: the companion loads it by name through `iCustom()`, so compiling
the EA proves nothing about the indicator, and the indicator is where every number on
the chart is produced.

`tests/test_build_evidence.py`-side checks (`tools/test_build_evidence.py`) fail if a
row claims PASS without a log, if a log is filed against the wrong program, or if the
list of files inside a log does not match that program's real include chain.

## Why the probe compiling is good news but not the finish line

`QSMC_ScannerProbe.mq5` is the **lightest** program here: it includes two headers, which
pull in five more, and it draws text only. It proves that this chain parses and links:

```
QSMC_ScannerProbe.mq5
├── QSMC_Preset.mqh      -> QSMC_Types.mqh
└── QSMC_Scanners.mqh    -> QSMC_Types.mqh, QSMC_MarketData.mqh, QSMC_Zones.mqh,
                            QSMC_Reaction.mqh, QSMC_Bias.mqh
```

The execution companion compiling is the more important half of that news: it means
the ladder added in PR #27 (`PipPointsFor` / `PipsToPrice` / `PlanTP` / `LadderClose` /
`ManagePipLadder` / `PosSlotInit` / `LadderKey`) is **compile-clean**, not merely
source-clean. It still does not prove the order path behaves; that needs a demo run.

Neither chain reaches:

- **`nadir2.mq5`** — the 43 359-line host that includes 23 headers and produces every
  number the chart shows. This is by far the most likely place for a compile error.
- **`QSMC_AutoTrader.mq5`** — the only file allowed to reach the trade API, and the one
  that now carries the `PipPointsFor()` / `PipsToPrice()` / `PlanTP()` / `LadderClose()` /
  `ManagePipLadder()` code added in PR #27. Nothing has compiled it yet.
- 16 of the 23 headers, which are not in the probe's chain.

## Coverage, counted

| | compile-clean by F7 | not compiled |
| --- | --- | --- |
| Programs | 2 of 4 (`QSMC_ScannerProbe`, `QSMC_AutoTrader`) | `nadir2.mq5`, `KLJ_DataFeeder.mq5` |
| Repository headers (23) | 8 | **15** |

The 15 headers no F7 has touched: `QSMC_AlertManager`, `QSMC_Arbiter`,
`QSMC_DataProvider`, `QSMC_EarlyBreakDetector`, `QSMC_Gates`, `QSMC_IncidentSafety`,
`QSMC_InputFingerprint`, `QSMC_LiquidityValue`, `QSMC_Renderer`, `QSMC_Root`,
`QSMC_Selftest`, `QSMC_Stats`, `QSMC_Structure`, `QSMC_UnifiedDecision`,
`QSMC_ZoneScorer`.

`nadir2.mq5` pulls in 20 of the 23, which is why one F7 on it is worth more than any
other single build: it is the only program that can prove the remaining 15 headers.

**One of them has a specific history.** `QSMC_InputFingerprint.mqh` was reported by
`docs/incident-20261101/fingerprint-fix/NOTE.md` as producing 32 MetaEditor errors;
the generator was repaired and the header regenerated, but that fix was explicitly
"not yet verified by F7" because no compiler was available. `nadir2.mq5` is its only
includer, so **the next F7 on the indicator is also the acceptance test for that fix**.
If it fails, read that NOTE first: it will almost certainly be a declarator-parsing
regression in `tools/generate_input_fingerprint.py`, not a hand-edit mistake.

## How to file the next result

1. In MetaEditor: open the file, press **F7**, wait for the "Errors" tab.
2. Copy the whole tail, including the file list and the `0 errors, N warnings, …` line.
3. Save it here as `YYYY-MM-DD_<Program>_F7.log` with a header saying what it proves
   and what it does not, then update the matrix above.
4. If warnings appear, keep them: a warning is evidence too, and the next reader needs
   to know which line produced it.

## Standing caveat

A source check is **not a compile**, and a compile is **not a profitable strategy**.
A clean F7 means the file **loads**. It says nothing about whether the strategy is
right, whether a parameter set is sane, or whether the account can afford the trade.
Those are separate claims, tested separately — and the last one (is it profitable?)
is not tested here at all, by design: there is no backtest in this repository and no
number in it should be read as an edge.
