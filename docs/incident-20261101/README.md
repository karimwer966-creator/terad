# `docs/incident-20261101/` — which subtree is authoritative, and for what

**This folder is frozen.** It is the evidence record of the 2026-11-01 incident
(v6.6.13) and of the F7 fix that followed it. Read it as a dated record, not as
a statement about the tree today. Nothing in here is instructions.

The question this README answers: there are two log subtrees, `evidence/` and
`fingerprint-fix/`, sharing 47 filenames, and until now no document said which
one to believe.

## Answer: neither supersedes the other — they are two phases

They are **not** two versions of the same evidence. `fingerprint-fix/` is a
re-run of the same suite set after one specific fix; `evidence/` is the run
before it. Each is the only record of something the other does not hold.

| Question | Authoritative subtree | Why |
|---|---|---|
| *Did the whole suite set pass after the F7 fix?* | **`fingerprint-fix/`** | 47 checks (`summary.txt`: `47 checks; failures: []`), one more than the earlier phase because the fix created `test_input_fingerprint_parser.py` — `fingerprint-fix/test_input_fingerprint_parser.log` exists and `evidence/` has no counterpart. |
| *Which gate failed, and why, per defect?* | **`evidence/`** | it is the only subtree holding the before-logs the report cites: `atr-before.log`, `authority-before.log`, `compact-before.log`, `instance-before.log`, `price-before.log`, `scanner-before.log`, `zone-before.log`, plus 8 `integration-before-*.log`. `fingerprint-fix/` has exactly one `before.log`, and it is about the fingerprint parser, not about any of those seven defects. |
| *What the narrative means / what was changed and where* | **`REPORT.md`** (this folder) | the prose. `REPORT.md:5` already states that `fingerprint-fix/` holds the later evidence and that the 46-check results in its own body describe the earlier phase. |

**Decidable — no user input needed.** The two subtrees are consistent with each
other; every difference between them is explained by the single fix.

## The whole difference between the two subtrees, measured

62 files in `evidence/`, 50 in `fingerprint-fix/`. 47 filenames are shared;
**44 of those 47 are byte-identical** (md5-verified). Three differ, and each
difference is the fingerprint fix showing through:

| File | `evidence/` | `fingerprint-fix/` | Cause |
|---|---|---|---|
| `summary.txt` | `46 checks; failures: []` | `47 checks; failures: []` | the new `test_input_fingerprint_parser.py` suite |
| `static_check.log` | `QSMC_InputFingerprint.mqh 97707 bytes` | `QSMC_InputFingerprint.mqh 98805 bytes` | the header was regenerated |
| `test_instance_identity.log` | `input fingerprint manifest: 568 inputs` | `input fingerprint manifest: 576 inputs` | the 8 `*End` inputs the comma-splitting fix recovered |

Only in `fingerprint-fix/`: `NOTE.md` (the fix write-up, in Arabic),
`before.log`, `test_input_fingerprint_parser.log`.
Only in `evidence/`: the 15 before/integration logs listed above.

There is no file present in both subtrees with conflicting content. The
duplicated logs — including `test_decision_journal.log`, which appears in both
at 325 lines — are byte-identical copies, not competing versions.

## Why both were kept

Deleting `evidence/` in favour of the newer run would destroy the only
before/after record for the seven defects `REPORT.md` argues from, and
`REPORT.md` cites those paths by name. Deleting `fingerprint-fix/` would throw
away the only post-F7-fix pass result in the repository. The 3 duplicated logs
cost 3 files.

## What these numbers are NOT

Both subtrees count a suite set that no longer exists, and both counts are now
stale by construction — a frozen log cannot be re-run:

| Claim inside this folder | True then | True now |
|---|---|---|
| `fingerprint-fix/NOTE.md` — "43 files `tools/test_*.py`" | yes | no — the tree holds 82 `test_*.py` (including the gate that checks this table) and 6 `check_*.py` |
| `fingerprint-fix/test_instance_identity.log` — "manifest: 576 inputs" | yes | no — `tools/test_instance_identity.py` reports **610** today |
| `static_check.log` — header 98,805 bytes | yes | no — 105,006 bytes today |
| `47 checks; failures: []` | yes, on 2026-11-01 | **not a statement about the current tree.** The current count is whatever `tools/*.py` returns when you run it. |

Neither subtree contains an F7 log from **after** the fix. `fingerprint-fix/NOTE.md`
says so itself: the platform verification it asks for — copy the regenerated
header, press F7 on `nadir2.mq5`, send back the compile log — was never
returned. That is still open.

## Scope of this folder

113 files, 9,185 lines of `.log`, all committed and preserved verbatim.
`REPORT.md` is written in Arabic and is the narrative; `fingerprint-fix/NOTE.md`
is also Arabic. This README is the only English entry point.

`tools/test_incident_evidence_map.py` asserts the counts and the identical/differing
split stated above, so a frozen log cannot be silently edited and this README
cannot drift away from the files it describes.
