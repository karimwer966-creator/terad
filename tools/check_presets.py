#!/usr/bin/env python3
"""Validate every shipped preset in presets/ against the MQL5 source it configures.

Why this exists
---------------
A `.set` file is opaque to the compiler: MQL5 accepts any line that looks like
`Name=value`, silently keeps the COMPILED DEFAULT for a name it does not know,
and silently keeps it for a value it cannot parse. A preset that drifts from
its source therefore still loads without a single log line - the operator
believes the file, the terminal believes the defaults, and nobody notices until
the trades differ from the runbook.

This gate closes that hole offline:

  * preset -> source mapping must be DECLARED by the preset itself, on a
    `; source: <path>` line, so moving a file cannot silently un-bind it;
  * every key must exist as an `input` of that source;
  * every value must parse as the declared type (bool/int/double/string), and
    every enum value must be a NUMBER that the source's enum actually declares.
    MT5 stores enums as integers; `InpX=QSMC_LOT_FIXED` is not a documented
    `.set` form, so it is normalised by `--fix`;
  * there is no inline-comment support in `.set`, so a `;` on a value line is
    treated as part of the value (that is exactly how a hand-typed rationale
    turns `true` into `true  ; why`);
  * safety invariants that no shipped preset may break: never arm REAL trading
    (InpAllowRealTrading=true) and never ship an account/server confirmation.

Usage
-----
  python3 tools/check_presets.py            # validate (exit 1 on any failure)
  python3 tools/check_presets.py --fix      # rewrite enum names as integers
  python3 tools/check_presets.py --list     # print the preset -> source table
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "presets"

SOURCE_RE = re.compile(r"^;\s*source:\s*(\S+)\s*$")
LINE_RE = re.compile(r"^([A-Za-z_]\w*)=(.*)$")
NEVER_ARM = ("InpAllowRealTrading",)
NEVER_FILL = ("InpRealAccountConfirm", "InpRealServerConfirm")

INT_TYPES = {"int", "long", "uint", "ulong", "short", "ushort", "char", "uchar"}

# Enums the terminal declares itself. A source file only declares its own enums,
# so these tables are the missing half of the picture: without them every
# timeframe input looks unresolvable and the preset keeps the compiled default.
BUILTIN_ENUMS = {
    "ENUM_TIMEFRAMES": {
        "PERIOD_CURRENT": 0, "PERIOD_M1": 1, "PERIOD_M2": 2, "PERIOD_M3": 3,
        "PERIOD_M4": 4, "PERIOD_M5": 5, "PERIOD_M6": 6, "PERIOD_M10": 10,
        "PERIOD_M12": 12, "PERIOD_M15": 15, "PERIOD_M20": 20, "PERIOD_M30": 30,
        "PERIOD_H1": 16385, "PERIOD_H2": 16386, "PERIOD_H3": 16387,
        "PERIOD_H4": 16388, "PERIOD_H6": 16390, "PERIOD_H8": 16392,
        "PERIOD_H12": 16396, "PERIOD_D1": 16408, "PERIOD_W1": 32769,
        "PERIOD_MN1": 49153,
    },
}


# --------------------------------------------------------------------------- #
# source model
# --------------------------------------------------------------------------- #
def read(path: Path) -> str:
    return io.open(path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")


def strip_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        quote = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                quote = not quote
            elif not quote and line[i:i + 2] == "//":
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def parse_input_list(text: str) -> list[tuple[str, str, str]]:
    """[(name, type, default)] in declaration order.

    `input int A = 9, B = 18;` declares TWO inputs on one line. Reading only the
    first one is how `InpAsianStart=9, InpAsianEnd = 18` once ended up inside a
    shipped .set: the second name was swallowed into the first value, the value
    stopped being a number, and the terminal ignored BOTH inputs.
    """
    text = strip_comments(text)
    out: list[tuple[str, str, str]] = []
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("input ") or s.startswith("input group"):
            continue
        body = s[len("input "):].strip()
        current_type = None
        for part in body.split(","):
            part = part.strip()
            m = re.match(r"^([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=(.*)$", part)
            if m:
                current_type = m.group(1)
                out.append((m.group(2), current_type, m.group(3).strip().rstrip(";").strip()))
                continue
            m = re.match(r"^([A-Za-z_]\w*)\s*=(.*)$", part)
            if m and current_type:
                out.append((m.group(1), current_type, m.group(2).strip().rstrip(";").strip()))
    return out


def parse_inputs(text: str) -> dict[str, tuple[str, str]]:
    """name -> (type, default-expression). Handles comma-separated declarations."""
    found: dict[str, tuple[str, str]] = {}
    for name, typ, default in parse_input_list(text):
        found[name] = (typ, default)
    return found


def parse_enums(text: str) -> dict[str, dict[str, int]]:
    """enum name -> {enumerator: value} for every enum with explicit values."""
    text = strip_comments(text)
    enums: dict[str, dict[str, int]] = {}
    for m in re.finditer(r"\benum\s+([A-Za-z_]\w*)\s*\{([^}]*)\}", text, re.S):
        members: dict[str, int] = {}
        nxt = 0
        for raw in m.group(2).split(","):
            raw = raw.strip()
            if not raw:
                continue
            if "=" in raw:
                name, val = raw.split("=", 1)
                name = name.strip()
                try:
                    nxt = int(val.strip(), 0)
                except ValueError:
                    nxt = None
                if nxt is None:
                    continue
            else:
                name = raw
                if nxt is None:
                    continue
            members[name] = nxt
            nxt += 1
        enums[m.group(1)] = members
    return enums


def enum_table(typ: str, source_enums: dict[str, dict[str, int]]) -> dict[str, int]:
    return source_enums.get(typ) or BUILTIN_ENUMS.get(typ) or {}


class Source:
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.path = ROOT / rel
        self.text = read(self.path)
        self.inputs = parse_inputs(self.text)
        self.enums = parse_enums(self.text)


_SOURCES: dict[str, Source] = {}


def source(rel: str) -> Source:
    if rel not in _SOURCES:
        _SOURCES[rel] = Source(rel)
    return _SOURCES[rel]


# --------------------------------------------------------------------------- #
# preset model
# --------------------------------------------------------------------------- #
class Preset:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.raw = io.open(path, encoding="utf-8", errors="replace", newline="").read()
        self.lines = self.raw.replace("\r\n", "\n").split("\n")
        self.source_rel = None
        self.values: list[tuple[int, str, str]] = []      # (line index, key, value)
        for i, line in enumerate(self.lines):
            m = SOURCE_RE.match(line)
            if m:
                self.source_rel = m.group(1)
            if not line.strip() or line.lstrip().startswith(";"):
                continue
            m = LINE_RE.match(line)
            if m:
                self.values.append((i, m.group(1), m.group(2)))

    def rewrite_enum(self, index: int, value: str) -> None:
        _, key, _ = self.values[[v[0] for v in self.values].index(index)]
        self.lines[index] = "%s=%s" % (key, value)


def preset_files() -> list[Path]:
    return sorted(p for p in PRESETS.glob("*.set") if p.is_file())


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate(p: Preset, fix: bool) -> list[str]:
    errs: list[str] = []
    if not p.source_rel:
        return ["no '; source: <path>' line - the preset is not bound to an EA/indicator"]
    if not (ROOT / p.source_rel).is_file():
        return ["'; source: %s' does not exist" % p.source_rel]

    src = source(p.source_rel)
    seen: set[str] = set()

    for idx, key, value in p.values:
        if key in seen:
            errs.append("duplicate key %s" % key)
        seen.add(key)
        if key not in src.inputs:
            errs.append("%s is not an input of %s" % (key, p.source_rel))
            continue
        typ, _default = src.inputs[key]

        if ";" in value:
            errs.append("%s=%r carries an inline ';' (no inline comments in .set)" % (key, value))
            value = value.split(";")[0].strip()

        if typ == "bool":
            if value.strip().lower() not in ("true", "false", "0", "1"):
                errs.append("%s=%r is not a bool" % (key, value))
        elif typ in INT_TYPES:
            if not re.fullmatch(r"[+-]?\d+", value.strip()):
                errs.append("%s=%r is not an integer" % (key, value))
        elif typ == "double" or typ == "float":
            try:
                float(value)
            except ValueError:
                errs.append("%s=%r is not a number" % (key, value))
        elif typ.startswith("ENUM_"):
            members = enum_table(typ, src.enums)
            token = value.strip()
            if re.fullmatch(r"[+-]?\d+", token):
                allowed = set(members.values())
                if allowed and int(token) not in allowed:
                    errs.append("%s=%s is not a value of %s (declared: %s)"
                                % (key, token, typ, sorted(allowed)))
            elif token in members:
                if fix:
                    p.lines[idx] = "%s=%d" % (key, members[token])
                else:
                    errs.append("%s=%s is an enumerator NAME; MT5 stores %s as an integer"
                                % (key, token, typ))
            else:
                errs.append("%s=%r is not a value of %s" % (key, token, typ))
        # strings: anything (MT5 writes them unquoted); nothing to check.

    for key in NEVER_FILL:
        if key in seen and get_value(p, key).strip() not in ("", '""'):
            errs.append("%s must ship empty (a preset must never name an account)" % key)
    for key in NEVER_ARM:
        if key in seen and get_value(p, key).strip().lower() in ("true", "1"):
            errs.append("%s=true: a shipped preset must never arm REAL trading" % key)
    return errs


def get_value(p: Preset, key: str) -> str:
    for _idx, k, v in p.values:
        if k == key:
            return v
    return ""


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    listing = "--list" in argv
    files = preset_files()
    if not files:
        print("FAIL presets/ is empty")
        return 1

    bad = 0
    for path in files:
        p = Preset(path)
        errs = validate(p, fix)
        if fix and p.lines != p.raw.replace("\r\n", "\n").split("\n"):
            nl = "\r\n" if "\r\n" in p.raw else "\n"
            io.open(path, "w", encoding="utf-8", newline="").write(nl.join(p.lines))
            print("FIXED %-46s enum names -> integers" % path.name)
        if listing:
            print("%-46s -> %s (%d keys)" % (path.name, p.source_rel or "UNBOUND", len(p.values)))
        if errs:
            bad += 1
            print("FAIL %s -> %s" % (path.name, p.source_rel or "UNBOUND"))
            for e in errs:
                print("       %s" % e)
        elif not listing:
            print("PASS %-46s %-42s %3d keys" % (path.name, p.source_rel, len(p.values)))

    if bad and not listing:
        print("\n%d preset(s) invalid. Fix the preset, never the source, and never "
              "silence a key that the EA does not declare." % bad)
        return 1
    if not listing and not fix:
        print("\n%d presets bound to their source, 0 invalid." % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
