# PREDICTIVE_ENGINE_AUDIT.md — this document does not exist in this repository

**This is a placeholder, not the original.** `PREDICTIVE_ENGINE_AUDIT.md` is cited by comments in
`nadir2.mq5` but was never committed here, so the citation resolved to nothing.
Rather than leave a dead link — or edit a 46,847-line file to remove a comment,
which would invalidate 291 pinned line citations — this stub records what is
known and where the current truth lives.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| `nadir2.mq5:1756` | *"CONTRACT (see …, section 7): - READ-ONLY with respect to the entry authority. The only function that can influence what the user reads as 'entry ready' is PMI_EntryGate(), and it can only TIGHTEN"* |

## What the citations imply

*Inferred.* An audit of the PMI (causal multi-timeframe market intelligence and
price-path research) layer. Section 7 stated the layer's contract: read-only
with respect to the entry authority, with `PMI_EntryGate()` the only function
able to influence "entry ready", and able only to tighten.

## Where the current truth lives

The PMI layer is 125 functions and 3,648 lines in `nadir2.mq5`, prefix `PMI_`.
Its contract is repeated at the citation site itself (`nadir2.mq5:1756-1760`)
and pinned by `tools/test_pmi_replay_audit.py` and
`tools/test_phase4_priceaction.py`.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
