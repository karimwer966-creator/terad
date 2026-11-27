# QSMC — Quantum SMC Intelligence Engine **v6.6.25**

Two MQL5 products live in this repository. They are not the same product, they do
not share a preset format contract, and only one of them is production-ready.

| Product | Files | State |
|---|---|---|
| **QSMC** (this repository's production product) | `nadir2.mq5` (canonical, mirrored to `MQL5/Indicators/`), `MQL5/Experts/QSMC_AutoTrader.mq5`, `MQL5/Include/QSMC/*.mqh`, 9 QSMC presets | offline verification via the curated gate below. The MT5 compile and the field tests are the operator's step — see [`docs/STAGED_GO_LIVE_LADDER_v6.6.14.md`](docs/STAGED_GO_LIVE_LADDER_v6.6.14.md) |
| **QATS** (separate, experimental) | `MQL5/Experts/QuantumAutonomousTradingSystem.mq5`, `presets/Quantum_XAUUSD_PRODUCTION.set` | **not production-ready**: no demonstrated edge. Read [`docs/QATS_README.md`](docs/QATS_README.md) first |

> **Install (Arabic):** [`INSTALL_AR.md`](INSTALL_AR.md) · **Everything indexed:** [`docs/INDEX.md`](docs/INDEX.md) · **Repo map:** [`docs/PROJECT_MAP_AR.md`](docs/PROJECT_MAP_AR.md)

## What ships

```
nadir2.mq5                          canonical host: 45 002 lines, 599 `input`
                                    declarations (65 of them groups), 47 enums,
                                    27 buffers / 7 plots - byte-identical mirror
                                    in MQL5/Indicators/nadir2.mq5
MQL5/Experts/QSMC_AutoTrader.mq5    the companion EA: 71 inputs, reads buffers 7-12
MQL5/Experts/KLJ_DataFeeder.mq5     feed sanity companion, no trading
MQL5/Include/QSMC/*.mqh             34 headers, aggregated by QSMC_Root.mqh
MQL5/Indicators/QSMC_ScannerProbe.mq5, QSMC_SmcVpEngine.mq5
MQL5/Scripts/QSMC_ArbiterTest.mq5, QSMC_ResetGuards.mq5
presets/*.set                       10 files, each bound to its source (see below)
tools/                              70 test suites, 98 Python files in total
                                    (gates, generators, simulators, fixtures)
docs/                               90 documents + docs/INDEX.md + docs/history/
```

## Presets — one file per decision, all validated offline

`tools/check_presets.py` proves that every `.set` binds to a real MQL5 source
(`; source:` line), that every key is a declared `input`, that every value parses
as its declared type, that every enum is the integer MT5 stores, and that **no
shipped preset can arm REAL trading**.

| Preset | For | What it does |
|---|---|---|
| `presets/nadir2_PRODUCTION_XAUUSD.set` | `nadir2` | full production input surface (542 keys, generated) |
| `presets/QSMC_v6.6.20_production_chart.set` | `nadir2` | display/declutter only, no decision change |
| `presets/QSMC_v6.6.20_latency_diagnosis.set` | `nadir2` | diagnostic logging, no trading |
| `presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set` | EA | the compiled defaults, printed as a file (demo armed, REAL refused) |
| `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set` | EA | master switch off + dry-run on: nothing is sent |
| `presets/QSMC_AutoTrader_DIAG_XAUUSD_M15.set` | EA | isolated demo observation: no entries or position management; [Arabic CORE log guide](docs/QSMC_CORE_DIAGNOSTICS_AR.md) |
| `presets/QSMC_AutoTrader_DEMO_0.10_200.set` | EA | 0.10 lots-risk, 200-currency daily stop (generated) |
| `presets/QSMC_AutoTrader_v6.6.22_SCALP_M5.set` | EA | M5 pin, 0.25 % risk, 08:00–20:00 window, 6 entries/day |
| `presets/QSMC_fixed005_tp100_200_300.set` | EA | fixed 0.05 lot, pip TP ladder 100/200/300 |
| `presets/Quantum_XAUUSD_PRODUCTION.set` | QATS | **other product** |

## XAUUSD/M15 trial bundle

Run `python3 tools/package_trial.py` to build `release/QSMC_XAUUSD_M15_Trial.zip`.
It contains the EA and indicator sources, a no-orders observation preset, an
optional DEMO order preset, and the [Arabic start guide](docs/QSMC_TRIAL_XAUUSD_M15_AR.md).
Compile both `.mq5` files with MetaEditor F7. The ZIP does not contain EX5s or
certify MT5 execution.

## Verify it yourself

```bash
python3 tools/check_repo_layout.py          # layout, presets, paths, version triple   (~0.2 s)
python3 tools/check_presets.py              # every .set against its source             (~0.4 s)
python3 tools/generate_set_presets.py --check   # derived presets vs the MQL5 source    (~0.2 s)
python3 tools/mql5_rules.py --quiet         # dialect rules                             (~1 s)
python3 tools/static_check.py               # static contracts                          (~2 s)
python3 tools/check_release_gate.py         # release gate (GO/NO-GO)                   (~5 s)
python3 tools/check_production_ready.py     # 63 curated checks: 64 suites + 4 gates    (~400 s)
```

CI runs the curated gate on every push (`.github/workflows/qsmc-verify.yml`),
plus the QATS verifier, the static/dialect jobs and the audit-report job.

## Safety contract (never edited by a preset)

- The EA refuses a REAL account until `InpAllowRealTrading=true` **and**
  `InpRealAccountConfirm` (exact login) **and** `InpRealServerConfirm` (exact
  server) all match; the refusal is logged, never silent.
- HARD ceilings (0.50 % risk, 2.00 % daily loss, 8.00 % account drawdown) cannot
  be exceeded by any input.
- Every order carries a server-side stop loss; there is no martingale and no
  stop widening anywhere in the code base.
- A preset never carries a login, a server name or an arming switch turned on:
  `tools/check_presets.py` fails the build if one ever does.

## History

Frozen, dated material (release reports, RCAs, audits of past versions) lives in
[`docs/history/`](docs/history/). Documents named `*_v6.6.x_*`, `*_AUDIT_*` or
dated `*_2026-*` describe the tree **as it was on that date**; they are not
statements about the current build.
