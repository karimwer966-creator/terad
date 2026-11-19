#!/usr/bin/env python3
"""Bundle the XAUUSD/M15 trial sources and two presets, not compiled EX5s."""
import argparse
import hashlib
import re
import subprocess
import zipfile
from pathlib import Path

from check_include_graph import PLATFORM_PREFIXES, includes_of

ROOT = Path(__file__).resolve().parents[1]
INDICATOR = "MQL5/Indicators/nadir2.mq5"
EA = "MQL5/Experts/QSMC_AutoTrader.mq5"
PRESETS = (
    ("01_OBSERVE_NO_ORDERS.set", "QSMC_AutoTrader_DIAG_XAUUSD_M15.set", False),
    ("02_DEMO_ORDERS.set", "QSMC_AutoTrader_v6.6.20_DEMO_AUTO.set", True),
)


def sources():
    """Follow the in-repository include closure of just the trial programs."""
    files = {}
    pending = [INDICATOR, EA]
    while pending:
        name = pending.pop()
        if name in files:
            continue
        data = (ROOT / name).read_bytes()
        files[name] = data
        for kind, target in includes_of(data.decode("utf-8")):
            if kind == "<" and target.startswith("QSMC/"):
                pending.append("MQL5/Include/" + target)
            elif kind != "<" or not target.startswith(PLATFORM_PREFIXES):
                raise ValueError(f"unbundled include in {name}: {target}")
    if files[INDICATOR] != (ROOT / "nadir2.mq5").read_bytes():
        raise ValueError("deployment indicator does not match canonical nadir2.mq5")
    return files


def preset(source, orders):
    data = (ROOT / "presets" / source).read_bytes()
    values = dict(line.split("=", 1) for line in data.decode("utf-8-sig").splitlines()
                  if line.strip() and not line.lstrip().startswith(";"))
    required = {
        "InpEnableTrading": "true" if orders else "false",
        "InpDryRun": "false" if orders else "true",
        "InpAllowRealTrading": "false",
        "InpRealAccountConfirm": "",
        "InpRealServerConfirm": "",
        "InpResetBreakersAtInit": "false",
        "InpPinTimeframeMinutes": "15",
        "InpIndicatorName": "nadir2",
    }
    for name, value in required.items():
        if values.get(name) != value:
            raise ValueError(f"{source}: expected {name}={value}")
    return data


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def build(output):
    files = sources()
    for name, source, orders in PRESETS:
        files[f"presets/{name}"] = preset(source, orders)
    files["START_HERE_AR.md"] = (ROOT / "docs/QSMC_TRIAL_XAUUSD_M15_AR.md").read_bytes()
    version = re.search(rb'#define\s+QSMC_VERSION_TEXT\s+"([^"]+)"', files[INDICATOR])
    if not version:
        raise ValueError("missing indicator build version")
    manifest = [
        "QSMC XAUUSD / M15 trial " + version[1].decode("ascii"),
        "checkout_commit=" + git("rev-parse", "HEAD"),
        "branch=" + git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_has_changes=" + ("yes" if git("status", "--porcelain") else "no"),
        "compile_status=Source only. Compile both MQ5 files with MetaEditor F7.",
        "terminal_verification=Not run by this packager.",
        "preset_01=Observation; leave Algo Trading off.",
        "preset_02=May send orders on DEMO. No REAL authorization or breaker resets.",
        "",
        "SHA-256  FILE",
    ]
    manifest.extend(f"{hashlib.sha256(data).hexdigest()}  {name}"
                    for name, data in sorted(files.items()))
    files["MANIFEST.txt"] = ("\n".join(manifest) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(output) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"CRC check failed: {bad_member}")
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "release/QSMC_XAUUSD_M15_Trial.zip")
    output = parser.parse_args().output
    if output.suffix.lower() != ".zip":
        parser.error("--output must end in .zip")
    count = build(output)
    print(f"{output} ({count} files, {output.stat().st_size:,} bytes)")
    print("SHA-256:", hashlib.sha256(output.read_bytes()).hexdigest())
    print("Source-only bundle: MetaEditor F7 required.")


if __name__ == "__main__":
    main()
