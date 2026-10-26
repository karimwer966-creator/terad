# QSMC EdgeBook and CSV storage contract

## Scope and safety

`CEdgeBook` in `MQL5/Include/QSMC/QSMC_Stats.mqh` stores setup lifecycle
records (pending setups followed by completed outcomes). It is a measurement
ledger, not a trading database or a probability model. The indicator/arbiter does not place, modify, or close orders.

- With `InpArbCSVLog=false` (default), outcomes are tracked in memory only; no
  files are created. With CSV logging enabled, both the signal journal and the
  EdgeBook are persisted.
- MQL5 `FileOpen` uses the terminal-local `MQL5/Files` sandbox. `FILE_COMMON`
  is not used by default. The repository's `Files/` directory is not the
  terminal runtime folder.
- Pending and completed records are flushed when written. This is event-driven,
  not per-bar I/O. A stable setup ID is reserved by its `PENDING` event and may
  transition to exactly one `OUTCOME`; duplicate events are rejected across restart.
- The in-memory ID hash table is bounded at 12,000 outcomes and strategy
  aggregates at 128 keys. Capacity exhaustion disables trusted summary output;
  it must never be treated as an incomplete-but-valid sample.

## EdgeBook V1 schema

One file per symbol and execution timeframe:

```text
QSMC_EDGE_V1_<symbol>_<timeframe>.csv
```

Header fields, in exact order:

```text
schema_version,record_type,setup_id,strategy_key,symbol,timeframe,entry_time,
direction,entry,stop,target,outcome,outcome_r,mfe_r,mae_r,spread_points,resolution
```

`schema_version=1`; `record_type` is exactly `PENDING` or `OUTCOME`. A pending
row has outcome `0` and resolution `PENDING`; its later outcome row must match
its stable setup identity and geometry. Existing files must match the full
header and every row's version, symbol, timeframe, finite numeric fields,
outcome class, stop/target geometry, and valid unique-ID lifecycle before their
aggregates are trusted. A malformed, partial, duplicate, or wrong-symbol row
marks the file **UNTRUSTED**; it is not silently repaired or appended to. Archive/repair
that file manually before reuse. This is intentionally fail-closed rather than
silently migrating or double-counting data.

Outcome classes are WIN, LOSS, BREAKEVEN, and AMBIGUOUS. The EdgeBook reports
per-strategy counts, average realized R, and an observed win rate with a 95%
Wilson interval only after the configured minimum sample. Wilson bounds describe
rate uncertainty only; they are not an estimate of profitability or future
performance. Strategy keys are versioned and group by source, timeframe,
direction, and zone role; the stable setup ID additionally includes symbol,
bar time, source, direction, and zone ID.

## Outcome resolution policy

- Closed OHLC bars only; no future bars are read.
- If stop and target are both touched inside one candle, the result is
  conservatively resolved as **stop first** (`BOTH_TOUCH_STOP_FIRST`).
- If only the target is touched, target is a win at the planned TP1 R multiple.
  If only the stop is touched, the result is -1R.
- A setup reaching the configured maximum observation horizon without either
  level being touched resolves on that final bar's close R: above +0.05R is a
  win, below -0.05R is a loss, otherwise breakeven.
- The candle that resolves at stop/target is excluded from MFE/MAE because OHLC
  cannot establish whether its high/low occurred before or after exit. Earlier
  closed bars are retained. The same closed bar cannot advance a row twice.

With `InpArbCSVLog=true`, each published setup is first appended as a
`PENDING` row (the same pending state is tracked in memory when persistence is
off). On restart, the EdgeBook loads those rows, finds each setup timestamp in
the available chart history, and replays subsequent closed bars through the
same stop/target/horizon rules before continuing live observation. A pending setup whose signal bar is no
longer present, or whose replay encounters invalid OHLC data, is closed as
`AMBIGUOUS` with `RESTART_HISTORY_GAP`; it is never guessed to be a win or loss.
The setup ID remains reserved throughout and the final `OUTCOME` row replaces
its pending status in memory. Completed outcomes and unresolved setups are both
protected against duplicate logging across restart.

The bounded pending row capacity matches the logger's 512 open-row limit. If
that or the 12,000-ID ledger capacity is exceeded, the system fails closed and
withholds trusted rates rather than evicting unresolved records.

## Signal journal V2

The optional signal journal is versioned separately and append-only per day:

```text
QSMC_ARB_V2_<symbol>_<timeframe>_<YYYYMMDD>.csv
```

Its 28-column header includes `schema_version`, `record_type`, deterministic
`setup_id`, candidate fields, and the zone-score `extra` breakdown. Existing
headers and rows are checked before appending. V1/unversioned files are left
untouched; there is no automatic destructive migration. A changed schema must
use a new versioned filename and preserve older files.

The signal journal is written only when `InpArbCSVLog=true`. Outcome tracking
still runs in memory with the setting off. MQL5 manages these files under its
own `MQL5/Files` sandbox; do not copy repository-relative paths into runtime
assumptions.

## Validation boundary

Run:

```bash
python3 tools/test_edgebook_contract.py
python3 tools/test_zone_scoring.py
python3 tools/check_release_gate.py
```

These are offline source/contract checks. They do not execute MetaTrader file
semantics, compile MQL5, validate broker-specific paths, or backtest outcomes.
Before any production claim, compile all four targets in MetaEditor and perform
an MT5 replay/paper run that checks append/restart behavior, same-bar resolution,
duplicate IDs, file permissions, and the configured MQL5 sandbox.
