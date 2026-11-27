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

The RXN layer itself, in `nadir2.mq5` — 86 functions, 2,826 lines, prefix
`RXN_`. Its contract is stated at the citation site, `nadir2.mq5:40188-40190`:
*"CLASSIFICATION ONLY. RXN never creates, mutates, invalidates, confirms or
authorizes a setup, and contains no trading function of any kind."*

**That contract is currently asserted by no offline suite.** No file in
`tools/` contains the string `CLASSIFICATION ONLY`, so it holds only because
the code happens to obey it. It is on the "recommended after F7" list in
[`ARCHITECTURE.md`](ARCHITECTURE.md) §9.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
