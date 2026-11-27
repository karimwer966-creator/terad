# QSMC_UNIFIED_DEMO_REAL_2026-11-09 — this document does not exist in this repository

**This is a placeholder, not the original.** It is cited by comments in two
shipped presets but was never committed here, so the citation resolved to
nothing.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| Citation | Text |
|---|---|
| `presets/QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set:26` | *"…all three re-verified before every order. See docs/QSMC_UNIFIED_DEMO_REAL_2026-11-09.md"* |
| `presets/QSMC_AutoTrader_v6.6.20_PRODUCTION_SAFE.set:10` | the same sentence |

## What the citations imply

*Inferred from those comments and from the date in the file name.* It described
the v6.6.20 change that unified DEMO and REAL execution into one engine: how the
account class is **detected** rather than typed in, and the three-part
authorization a REAL account needs — `InpAllowRealTrading=true`, plus
`InpRealAccountConfirm` matching this exact login, plus `InpRealServerConfirm`
matching this exact server — re-verified at init and again before every order.

## Where the current truth lives

All of it is in the source and is verified, not merely described:

| Fact | Where |
|---|---|
| one engine, mode detected from `ACCOUNT_TRADE_MODE` | `MQL5/Experts/QSMC_AutoTrader.mq5:1121` `ExecutionModeName()`, `:1131` `RealProfileActive()` |
| the three hard ceilings the presets quote | `:1310` `HardMaxRiskPercent() = 0.50`, `:1138` `HardMaxAggregateRiskPercent() = 2.00`, `:1312` `HardMaxDDPercent() = 8.00` |
| the arming inputs | `:313` `InpAllowRealTrading` (default **false**), `:315` `InpRealServerConfirm` |
| the five inputs that size the order | [`EA_RISK_INPUTS.md`](EA_RISK_INPUTS.md) |
| the contract that all of this obeys | `tools/test_execution_safety.py`, block **D9** — DEMO cannot become REAL, REAL never arms itself, identity drift latches an emergency lockout |

The `0.50% / 2.00% / 8.00%` figures the presets quote are correct as of v6.6.25
and are repeated in the source comment at `:1307`.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
