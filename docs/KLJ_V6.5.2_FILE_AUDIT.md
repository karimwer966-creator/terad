# KLJ_V6.5.2_FILE_AUDIT.md — this document does not exist in this repository

**This is a placeholder, not the original.** `KLJ_V6.5.2_FILE_AUDIT.md` is cited by comments in
`nadir2.mq5` but was never committed here, so the citation resolved to nothing.
Rather than leave a dead link — or edit a 46,847-line file to remove a comment,
which would invalidate 291 pinned line citations — this stub records what is
known and where the current truth lives.

Everything below is either a verified fact about this tree or is explicitly
labelled as inferred from the citing comment. **No content of the original has
been reconstructed.**

## What cites it

| `nadir2.mq5:143` | *"AUDIT-05 [STYLE] Dead declarations removed (4 unused entry-mark buffer arrays, 1 undefined prototype) … Report: …"* |
| `nadir2.mq5:119` | *"v6.5.2 FILE-BY-FILE AUDIT PASS (this build): AUDIT-01 [CRITICAL] Indicators-Access: a short/failed CopyBuffer was treated as 'data available'"* |

## What the citations imply

*Inferred.* A file-by-file audit of the v6.5.2 build, numbered AUDIT-01 …
AUDIT-05. AUDIT-01 was the significant one: a short or failed `CopyBuffer` was
being treated as "data available", so the full path ran on data it did not have.

## Where the current truth lives

The buffer contract those calls feed is written down now:
[`BUFFER_CONTRACT.md`](BUFFER_CONTRACT.md).

On the CopyBuffer guards specifically, be precise about what is verified. The
v6.6.25 release review read every `CopyBuffer` site in `nadir2.mq5` and found
all 21 guarded within one to three lines — that was a manual read, recorded in
the review, **not** an automated gate. `tools/static_check.py` lists
`CopyBuffer` only in its API allowlist; it does not check that a copy is
bounds-checked. `tools/test_el_data_integrity.py` executes shipped copy-gate
bodies against deterministic terminal stubs, which is the closest thing to a
gate for this defect class.

---

This stub exists so `tools/test_tool_reference_integrity.py` can report zero
dangling citations. It carries no authority: if the original document is ever
recovered, it replaces this file.
