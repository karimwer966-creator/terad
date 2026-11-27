# KLJ_V6.5.4_REACTION_CONFLICT_FIX.md — this document does not exist in this repository

**This is a placeholder, not the original.** `KLJ_V6.5.4_REACTION_CONFLICT_FIX.md` is cited by comments in
`nadir2.mq5` but was never committed here, so the citation resolved to nothing.
Rather than leave a dead link — or edit a 46,847-line file to remove a comment,
which would invalidate 291 pinned line citations — this stub records what is
known and where the current truth lives.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| `nadir2.mq5:55` | header banner: *"v6.5.4 REACTION CONFLICT FIX (see …)"* |
| `docs/KLJ_V6.6.0_SIGNAL_ARBITRATION.md:7` | *"its own comments refer to `docs/KLJ_V6.5.4_REACTION_CONFLICT_FIX.md`"* |
| `docs/KLJ_V6.6.0_SIGNAL_ARBITRATION.md:713` | listed as **absent from this checkout**, with the note *"if they contain thresholds that contradict anything above, they win"* |

## What the citations imply

*Inferred from `nadir2.mq5:55-60`.* Two fixes: (1) *"(no liquidity pool in
range)"* no longer earns 8 of 12 score points — missing liquidity evidence now
scores 0, on the scale swept 12 > resting 4 > none 0; (2) `RXN_ApplyOpposition`
caps a CONFIRMED reaction at CONFLICTED (REACTION).

## Where the current truth lives

Both rules are in `nadir2.mq5`. Note that
[`KLJ_V6.6.0_SIGNAL_ARBITRATION.md`](KLJ_V6.6.0_SIGNAL_ARBITRATION.md) explicitly
subordinates itself to this document, so treat its thresholds as unverified
where they concern liquidity scoring. `tools/check_repo_layout.py` previously
allowlisted this path as *"documented as absent from this checkout"*; that entry
is no longer needed now that this stub exists.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
