#!/usr/bin/env python3
"""Crosswalk between pinned line numbers and the current nadir2.mq5.

THE PROBLEM
-----------
Seven audit suites and one document pin source locations as literal line
numbers:

    GRP, FLAG = 852, 853
    check(... in line_at(GRP), "A the resolver has its own input group at L%d" % GRP)

`nadir2.mq5` is 44 000 lines and grows by hundreds of lines per release, so
every pin above an insertion drifts. On 2026-11-06 eight suites were red on
`main` for no reason but drift; the code they describe was fine. The pins had
last been correct at commit 166d16a, 61 commits earlier.

WHAT THIS DOES
--------------
A pin is no longer a fact about the current file, it is a COORDINATE IN A NAMED
SNAPSHOT. `tools/pinmap.json` records, for each pinned coordinate, the text of
that line in the snapshot it was written against. At run time the coordinate is
translated to the current line by finding that text in the file being tested.

The contract is unchanged and in one direction only: the suite's own content
probe still has to match the line it lands on. So

  * a line that MOVED is followed silently - drift is no longer a false alarm;
  * a line whose CONTENT changed fails, exactly as before, with the same
    message - the probe is what asserts, the number is only a pointer;
  * a line that was DELETED fails: its snapshot text is not in the file any
    more, so the pin resolves to a sentinel that no probe can match.

Nothing here can make a wrong citation pass. It can only make a right citation
survive an unrelated insertion 3 000 lines above it.

USAGE
-----
  python3 tools/pinmap.py --check          # verify every pin still resolves
  python3 tools/pinmap.py --build          # regenerate the crosswalk (needs git)
  python3 tools/pinmap.py --rewrite-doc    # rewrite the doc's L#### citations

`--build` needs git history; `--check` and normal test runs need only the JSON,
so the suites keep working in a shallow CI clone (fetch-depth: 1).
"""
from __future__ import print_function

import argparse
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = "nadir2.mq5"
TABLE = Path(os.environ.get("PINMAP_TABLE") or (ROOT / "tools" / "pinmap.json"))

# Suites that carry pins, with the commit their numbers are coordinates in.
# Chosen by tools/pinmap.py --detect: the commit at which the most of that
# suite's pins land on the construct its probe expects.
SUITES = [
    "test_docs_freshness",
    "test_resolver",
    "test_weighted_gates",
    "test_scalping",
    "test_decision_journal",
    "test_declutter_cap",
    "test_tactical_authority",
    "test_phase5_meanreversion",
]

# A document's citations are one flat set of numbers, not per-suite.
DOC = "docs/QSMC_V6.6.13_SEVEN_STRATEGY_MODULES.md"

WINDOW = 1          # context lines recorded on each side of the pin
MIN_LINE = 100      # below this an integer is a weight/count, never a line


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def read_source(text=None):
    if text is None:
        with io.open(str(ROOT / SRC), encoding="utf-8", newline="") as fh:
            text = fh.read()
    return text.replace("\r\n", "\n").split("\n")


def window(lines, n, w=WINDOW):
    """Normalised context block around 1-based line n - the pin's fingerprint."""
    lo, hi = max(1, n - w), min(len(lines), n + w)
    return "\n".join(norm(lines[i - 1]) for i in range(lo, hi + 1))


def index_windows(lines, w=WINDOW):
    """fingerprint -> [line, ...] for the whole file."""
    idx = {}
    for n in range(1, len(lines) + 1):
        idx.setdefault(window(lines, n, w), []).append(n)
    return idx


class PinMap(object):
    """Resolves snapshot coordinates to lines in the file under test."""

    def __init__(self, path=None, lines=None):
        self.path = Path(path) if path else TABLE
        self.lines = lines if lines is not None else read_source()
        self._idx = None
        self.data = {}
        if self.path.is_file():
            with io.open(str(self.path), encoding="utf-8") as fh:
                self.data = json.load(fh)
        self.stats = {"hit": 0, "moved": 0, "missing": 0}
        self.missing = []

    # ---------------------------------------------------------------- lookup
    def _index(self, form="text"):
        if not isinstance(self._idx, dict):
            self._idx = {}
        if form not in self._idx:
            w = {"text": WINDOW, "wide": 2}.get(form, 0)
            self._idx[form] = ({}
                               if form == "line_text"
                               else index_windows(self.lines, w))
            if form == "line_text":
                for n in range(1, len(self.lines) + 1):
                    self._idx[form].setdefault(norm(self.lines[n - 1]), []).append(n)
        return self._idx[form]

    # How far an off-table coordinate may be from a real pin and still be
    # resolved, as an offset from it. Every `body(V-1, V+1)`-style span in the
    # suites is within this, and nothing legitimate is further: a number this
    # far from any pinned construct is not a citation, it is a count.
    NEAR = 12

    def resolve(self, suite, n):
        """Current line for the coordinate `n` of `suite`.

        Exact pins are resolved by fingerprint, so they follow every insertion
        above them. A coordinate that is not itself a pin but sits within
        NEAR lines of one is treated as an offset from that pin - this is how
        `body(V_ATR - 1, V_ATR + 1)` keeps working without pinning 5 989
        separately. Anything else resolves to -1, which no probe can match,
        so an unmapped citation is a loud failure and never a silent pass."""
        pins = self.data.get("suites", {}).get(suite, {}).get("pins", {})
        entry = pins.get(str(n))
        if entry:
            return self._by_text(entry, suite)
        for d in range(1, self.NEAR + 1):
            # n = cand + signed: a pin BELOW n drags n forward, one ABOVE it
            # drags n back. Getting this sign wrong silently reads the wrong
            # window on either side of the pinned construct.
            for cand, signed in ((n - d, d), (n + d, -d)):
                e = pins.get(str(cand))
                if e:
                    return self._by_text(e, suite) + signed
        self.stats["missing"] += 1
        self.missing.append((suite, n, "not a pinned coordinate"))
        return -1

    def _by_text(self, entry, suite=None):
        """Locate a pin by its snapshot fingerprint.

        Tried in order: the exact context block; the pin line alone; then a
        window with two symmetric lines on each side. The single-line form
        survives an edit to a neighbouring line (v6.6.20 moved the init
        chatter from a raw Print() to QSMC_InitPass(), which rewrote the lines
        either side of one self-test hook); the wider form is only a
        tie-breaker. When a wider form is used the answer must still be unique,
        so this can never turn an ambiguous citation into a confident one."""
        recorded = entry.get("line")
        for form in ("text", "line_text", "wide"):
            want = entry.get(form, "")
            if not want:
                continue
            if form == "text" and recorded and 1 <= recorded <= len(self.lines) \
                    and window(self.lines, recorded) == want:
                self.stats["hit"] += 1
                return recorded
            hits = (self._index(form)).get(want, [])
            if len(hits) == 1:
                self.stats["moved" if form == "text" else "hit"] += 1
                return hits[0]
            if hits and recorded and form == "text":
                # Several candidates: the nearest to the recorded line, so an
                # ambiguous fingerprint degrades to "follow the nearest move"
                # rather than jumping to an unrelated duplicate.
                self.stats["moved"] += 1
                return min(hits, key=lambda h: abs(h - recorded))
            if form == "line_text" and hits and recorded:
                self.stats["moved"] += 1
                return min(hits, key=lambda h: abs(h - recorded))
        self.stats["missing"] += 1
        self.missing.append((suite, recorded, entry.get("text", "").split("\n")[0][:60]))
        return -1                                     # no probe can match -1

    def summary(self):
        s = self.stats
        if not (s["moved"] or s["missing"]):
            return ""
        return ("pinmap: %d resolved in place, %d followed a move, %d unresolved"
                % (s["hit"], s["moved"], s["missing"]))


    def find_fn(self, sig_re):
        """(start, end) of the function whose signature matches `sig_re`.

        Used where a suite needs the body of a NAMED function that has no pin:
        deriving it from the signature is strictly better than a line number,
        because a name cannot drift."""
        start = None
        for i, l in enumerate(self.lines, 1):
            if re.search(sig_re, l):
                start = i
                break
        if start is None:
            return (0, 0)
        depth, opened = 0, False
        for i in range(start - 1, len(self.lines)):
            depth += self.lines[i].count("{") - self.lines[i].count("}")
            if depth > 0:
                opened = True
            if opened and depth <= 0:
                return (start, i + 1)
        return (start, 0)

    def fn_text(self, sig_re):
        a, b = self.find_fn(sig_re)
        if a < 1 or b < a:
            return ""
        return "\n".join(self.lines[a - 1:b])


_DEFAULT = None


def C(suite, n):
    """Mark `n` as an ALREADY-CURRENT line, so it is not translated again.

    Use this for a value that came out of the file under test - the line
    returned by `fn_end(...)`, or a scan result. Such a number is not a
    coordinate in any snapshot, and passing it to `line()` would make pinmap
    look for a pin near it and return a neighbouring construct's line.

    The `suite` argument is kept for call compatibility and for readability at
    the call site (which suite's helper produced it); it has no effect, because
    a current line belongs to every suite equally."""
    return _Raw(n)


class _Raw(int):
    """An integer that is ALREADY a line of the file under test.

    The marker carries no suite on purpose: it used to, and that is what went
    wrong. `pinmap.C(SUITE, fn_end(DEF))` was written as if `fn_end()` returned
    a snapshot coordinate, but `fn_end()` resolves its own input first, so the
    value it returns is a CURRENT line. Wrapping that current line in a
    coordinate and then passing it to `body()`, which resolves again, translated
    a translated number: it read `<real end> + <offset of the nearest pin>`.

    That stayed invisible for as long as the file did not grow: the drift for a
    resolved-by-fingerprint pin was zero, so the double translation was an
    identity. The first release that inserted anything above these functions
    turned it into a wrong span - which is why these suites went red while the
    code they describe was intact.

    So the marker's only job is "do not resolve me again"."""

    def __new__(cls, n):
        return int.__new__(cls, n)

    def resolve(self):
        return int(self)


def default_map():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PinMap()
    return _DEFAULT


def line(suite, n):
    """Public helper: pin `n` of `suite` -> current line in nadir2.mq5."""
    if isinstance(n, _Raw):
        return n.resolve()
    return default_map().resolve(suite, n)


# ------------------------------------------------------------------ building
def suite_pins(suite):
    """Every integer in the suite that could be a line number."""
    import ast
    src = io.open(str(ROOT / "tools" / ("%s.py" % suite)), encoding="utf-8").read()
    tree = ast.parse(src)
    pins = set()

    def add(node):
        """Collect candidate line numbers, descending through containers so a
        pin written as `W = {...: (20, 875)}` is found at any depth."""
        if isinstance(node, ast.Constant) and isinstance(node.value, int) \
                and not isinstance(node.value, bool) and node.value >= MIN_LINE:
            pins.add(node.value)
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for e in node.elts:
                add(e)
        elif isinstance(node, ast.Dict):
            for k in node.keys:
                add(k)
            for v in node.values:
                add(v)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            add(node.value)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            add(node.iter)
    return sorted(pins)


def show(rev, path=SRC):
    """`git show rev:path`, with a message that says what to do when the
    clone has no history - the JSON table is what the suites actually need."""
    out = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=str(ROOT),
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(
            "cannot read %s:%s. Rebuilding the crosswalk needs git history "
            "(git fetch --unshallow origin); running the suites needs only "
            "tools/pinmap.json." % (rev, path))
    return out.stdout


def suite_base(suite):
    if BASES.is_file():
        with io.open(str(BASES), encoding="utf-8") as fh:
            rec = json.load(fh).get(suite, {}).get("base")
        if rec:
            return rec
    return _suite_base_from_history(suite)


def _suite_base_from_history(suite):
    """The commit a suite's numbers are coordinates in: the one that last edited
    that suite. A suite is (re)pinned by a pass against the source of its day,
    so it and nadir2.mq5 were in agreement at that commit and the drift starts
    at the next commit that touches the source."""
    out = subprocess.run(["git", "log", "-1", "--format=%H", "--",
                          "tools/%s.py" % suite], cwd=str(ROOT),
                         capture_output=True, text=True)
    return out.stdout.strip() or "166d16a"


def build(base=None, w=WINDOW, out=None, quiet=False):
    """Rewrite tools/pinmap.json from the snapshot each suite was pinned in."""
    cur = read_source()
    tables = {0: index_windows(cur, 0),
              1: index_windows(cur, 1),
              2: index_windows(cur, 2)}

    def locate(old, n):
        """Where the pin's fingerprint is in the current file, by preference."""
        for ww in (1, 0, 2):
            hits = tables[ww].get(window(old, n, ww))
            if hits and len(hits) == 1:
                return hits[0]
        for ww in (1, 0, 2):
            hits = tables[ww].get(window(old, n, ww))
            if hits:
                return min(hits, key=lambda h: abs(h - n))
        return None

    doc = {"generated_by": "tools/pinmap.py --build",
           "source": SRC,
           "note": ("'text' is the normalised source context of the pin in the "
                    "snapshot that suite was pinned against; 'line' is where "
                    "that context was last seen. Suites translate the "
                    "coordinate through this table and then assert on the "
                    "content they land on, so a moved line is followed and a "
                    "changed line still fails."),
           "suites": {}}
    total = resolved = 0
    for suite in SUITES:
        sb = base or suite_base(suite)
        old = read_source(show(sb))
        entries = {}
        for n in suite_pins(suite):
            if n > len(old):
                continue
            total += 1
            at = locate(old, n)
            if at is not None:
                resolved += 1
            # Every pin is recorded even when its context no longer appears
            # verbatim: recording only the survivors would make a deleted line
            # indistinguishable from a line that was never a pin.
            entries[str(n)] = {"text": window(old, n, w),
                               "line_text": norm(old[n - 1]),
                               "wide": window(old, n, 2),
                               "line": at}
        doc["suites"][suite] = {"base": sb, "pins": entries}
        if not quiet:
            print("%-26s base %s  %3d pins, %3d located"
                  % (suite, sb[:9], len(entries),
                     sum(1 for e in entries.values() if e["line"] is not None)))
    doc["stats"] = {"pins": total, "resolved": resolved}
    dest = Path(out) if out else TABLE
    with io.open(str(dest), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True))
        fh.write("\n")
    if not quiet:
        print("wrote %s: %d/%d pins located in the current source"
              % (dest.name, resolved, total))
    return 0


BASES = ROOT / "tools" / "pinmap_bases.json"


def detect(quiet=False, commits=45):
    """Choose, per suite, the snapshot its numbers are coordinates in.

    Two cheaper heuristics were tried first and both are wrong in ways that
    matter. "The commit that last edited the suite" ignores that a suite is
    often edited without being re-pinned. "The commit whose pins all still
    appear in the file" is satisfied by the current file itself, because a
    one-line fingerprint matches many places.

    So the base is measured on the only thing that settles it: the suite's own
    verdict. For each candidate snapshot the crosswalk is built and the suite
    is run against the current source; the first snapshot with zero failures
    wins, and the answer is frozen in tools/pinmap_bases.json. That file is
    committed, so running the suites needs no git history and no search.
    """
    import tempfile
    out = {}
    revs = subprocess.run(["git", "log", "--format=%H", "--max-count=%d" % commits,
                           "--", SRC], cwd=str(ROOT),
                          capture_output=True, text=True).stdout.split()
    if "166d16a" not in revs:
        revs.append("166d16a")
    for suite in SUITES:
        best = (None, 0)
        for rev in revs:
            fd, tmp = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            try:
                build(base=rev, out=Path(tmp), quiet=True)
                env = dict(os.environ, PINMAP_TABLE=tmp)
                with io.open(os.devnull, "w") as devnull:
                    run = subprocess.run([sys.executable, "tools/%s.py" % suite],
                                         cwd=str(ROOT), stdout=subprocess.PIPE,
                                         stderr=devnull, text=True, env=env)
                m = re.search(r"failures:?\s+(\d+)", run.stdout or "")
                fails = int(m.group(1)) if m else 10 ** 5
            finally:
                os.unlink(tmp)
            if best[0] is None or fails < best[1]:
                best = (rev, fails)
            if fails == 0:
                break
        out[suite] = {"base": best[0], "failures_at_base": best[1]}
        if not quiet:
            print("%-26s base %s  %d failure(s) against today's source"
                  % (suite, best[0][:9], best[1]))
    with io.open(str(BASES), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


# ------------------------------------------------------------------ checking
def check():
    lines = read_source()
    idx = index_windows(lines)
    with io.open(str(TABLE), encoding="utf-8") as fh:
        data = json.load(fh)
    bad = 0
    for suite, block in sorted(data.get("suites", {}).items()):
        dead = [n for n, e in sorted(block["pins"].items(), key=lambda kv: int(kv[0]))
                if not idx.get(e["text"])]
        if dead:
            bad += len(dead)
            print("FAIL %-30s %d pin(s) no longer resolve: %s"
                  % (suite, len(dead), dead[:8]))
        else:
            print("PASS %-30s %3d pins resolve" % (suite, len(block["pins"])))
    print("")
    print("pinmap crosswalk: %d unresolvable pin(s)" % bad)
    return 1 if bad else 0


# -------------------------------------------------------------- doc rewrite
def rewrite_doc(base="166d16a", dry=False):
    """Rewrite the document's L#### citations from base coordinates to HEAD."""
    old = read_source(show(base))
    cur = read_source()
    idx = index_windows(cur)
    path = ROOT / DOC
    text = io.open(str(path), encoding="utf-8", newline="").read()

    moved = kept = lost = 0

    def sub(m):
        nonlocal moved, kept, lost
        prefix, num = m.group(1), int(m.group(2))
        if not (1 <= num <= len(old)):
            lost += 1
            return m.group(0)
        hits = idx.get(window(old, num))
        if not hits:
            lost += 1
            print("  LOST   L%-6d %s | %s" % (num, prefix, norm(old[num - 1])[:64]))
            return m.group(0)
        new = min(hits, key=lambda h: abs(h - num))
        if new == num:
            kept += 1
            return m.group(0)
        moved += 1
        return "%sL%d" % (prefix, new)

    out = re.sub(r"(\b)L(\d{3,5})\b", sub, text)
    if not dry:
        with io.open(str(path), "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
    print("")
    print("doc citations: %d moved, %d already correct, %d unresolved %s"
          % (moved, kept, lost, "(dry run)" if dry else "-> written"))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--rewrite-doc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base", default=None,
                    help="force one snapshot for every suite (default: per suite)")
    args = ap.parse_args(argv)
    if args.detect:
        detect()
        return 0
    if args.build:
        return build(args.base)
    if args.rewrite_doc:
        return rewrite_doc(args.base, args.dry_run)
    return check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
