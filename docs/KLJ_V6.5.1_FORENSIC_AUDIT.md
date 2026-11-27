# KLJ_V6.5.1_FORENSIC_AUDIT.md — this document does not exist in this repository

**This is a placeholder, not the original.** `KLJ_V6.5.1_FORENSIC_AUDIT.md` is cited by comments in
`nadir2.mq5` but was never committed here, so the citation resolved to nothing.
Rather than leave a dead link — or edit a 46,847-line file to remove a comment,
which would invalidate 291 pinned line citations — this stub records what is
known and where the current truth lives.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| `nadir2.mq5:1859` | *"these are FIXED reference market clocks in UTC. They are deliberately NOT the same model as the user-configurable killzones … the divergence is documented in …"* |

## What the citations imply

*Inferred.* A forensic audit of the v6.5.1 build. The citation that survives is
a specific one: it explains why the PMI layer's fixed UTC session windows
(`PMI_UTC_ASIA_START` … , `nadir2.mq5:1860+`) are deliberately a different model
from the operator-configurable killzones (`InpAsianStart`,
`InpLondonKillZoneStart`, `InpNewYorkKillZoneStart`) that drive `IsInSession()`.

## Where the current truth lives

Both models are in `nadir2.mq5` and both are inputs, so the divergence is
readable directly: the `PMI_UTC_*` `#define`s from `nadir2.mq5:1860`, and the
killzone inputs listed in [`INPUTS_REFERENCE.md`](INPUTS_REFERENCE.md). The
dead-code note above the citation (an unreachable `h>=16 && h<21 -> NEWYORK`
branch) is resolved in the current source.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
