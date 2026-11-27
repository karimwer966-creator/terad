# KLJ_V6.5.0_REACTION_LAYER_AUDIT.md — this document does not exist in this repository

**This is a placeholder, not the original.** `KLJ_V6.5.0_REACTION_LAYER_AUDIT.md` is cited by comments in
`nadir2.mq5` but was never committed here, so the citation resolved to nothing.
Rather than leave a dead link — or edit a 46,847-line file to remove a comment,
which would invalidate 291 pinned line citations — this stub records what is
known and where the current truth lives.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| `nadir2.mq5:202` | header banner, v6.5.0 build notes: *"No existing threshold was changed; no gate was loosened; no engine was duplicated. Audit: …"* |
| `nadir2.mq5:4451` | `// WHY THIS LAYER EXISTS (audit: …)` above the RXN type declarations |
| `nadir2.mq5:40188` | `// WHY (audit: … sections 5 and 21)` above the RXN classification block |

## What the citations imply

*Inferred from those comments, not from the document.* It audited the v6.5.0
REACTION signal layer (RXN) and its sections 5 and 21 explained why RXN exists:
ZRE (Layer D) detects a closed-bar zone rejection correctly, but the only object
it can publish, `SZRESignal`, is gated on full execution geometry
(`RR1 >= InpMinRR1` and `score >= InpZREMinScore`), so when either fails nothing
is published at all. RXN was added as a **classification-only** layer to close
that gap.

## Where the current truth lives

The RXN layer itself, in `nadir2.mq5` — 86 definitions, 2,826 lines, prefix
`RXN_`. Its contract is stated at the citation site, `nadir2.mq5:40185-40186`:
*"CLASSIFICATION ONLY. RXN never creates, mutates, invalidates, confirms or
authorizes a setup, and contains no trading function of any kind."*

**That contract is now asserted by `tools/test_rxn_classification_only.py`**
(51 checks). It scans **all 86** RXN definitions, and the suite pins that fact:
two earlier drafts of its parser matched only 65, then 85, because the signature
scan stopped too soon — and the one it was still missing at 85 was
`RXN_Classify`, the layer's decision core. A gate that skips the function it
exists to check reports green for nothing, so the count is an assertion, not a
comment. It asserts: no trading,
order, position or account API anywhere in the layer; no signal buffer written or
even named; no write to `g_final_signal`, `g_res_score`, `SigLog_Buf*` or
`MarkCoreEntry`; and that the set of non-RXN functions touching any `g_rxn_*`
global is **exactly** the seven it enumerates, each with a pinned read-site
count, so a new reader fails the gate even if it is harmless.

It does not claim "RXN touches nothing", because that is not true and a false
absolute is worse than a bounded one. RXN state reaches two places, and both are
named and pinned:

* `ResolveFinalSignal` reads `g_rxn_best_buy` at `:6309` for the resolver's
  reaction vote (weight `InpResWeightReaction = 30`, `:906`) — behind
  `InpUseFinalResolver`, which **defaults to `false`** (`:901`), and
  `g_final_signal` reaches only the journal (`:6698`) and the dashboard status
  text (`:34574`), never an order call.
* `g_rxn_extra_zones` reaches the weighted gate's room leg via
  `AlertOpposingRoomATR` (`:42781`) → `opposing_room_atr` → `:43067`. But that
  array is **supplied by `ZRE_Update`** (`:40146-40148`) from the zones ZRE
  dropped; `RXN_RankExtra` (`:43576`) only sorts it and `RXN_Clear` (`:43997`)
  only empties it. RXN classifies those zones, it does not produce them.

This item is therefore **closed**. An earlier draft of this stub said it was on
the "recommended after F7" list in
[`ARCHITECTURE.md`](ARCHITECTURE.md) §9; it was not — §9 never mentioned RXN, and
the gap was recorded only here.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
