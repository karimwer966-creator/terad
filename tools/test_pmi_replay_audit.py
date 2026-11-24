#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PMI REPLAY AUDIT (P0-3) - a verdict with nothing behind it is not a PASS.

WHY THIS EXISTS
---------------
The owner's 2026-11-24 MT5 journal contained ``CAUSALITY PASS (digests 1,
comparisons 0)``. The PMI replay audit really did compare nothing on the first
closed-bar passes (the ring is cold; re-derivation needs a stable window),
and the print still said PASS. Worse, the scenario self-test printed
``[PMI SelfTest] PASS - Tests 1-4, 6`` naming a test 5 that has never existed.

This suite pins the v6.6.24 (audit P0-3) contract:

  * the tri-state verdict helpers (PMI_TriStateVerdict / PMI_VerdictText) are
    executed natively — zero checked items can NEVER yield PASS;
  * the replay report is assembled through those helpers and carries an
    explicit "Overall PASS|INCONCLUSIVE|FAIL" prefix;
  * the cold-start skip is loud, sets last_report truthfully and states the
    arming condition (instead of an invisible `return`);
  * the scenario self-test counts the scenarios it executed and cannot print
    PASS off zero executions, and its PASS line no longer names a phantom
    "Tests 1-4, 6".

What this is NOT: an MQL5 compile, a Strategy Tester run, or evidence that any
audit actually compared anything on the operator's machine. It is the
arithmetic and the source contract. F7 in MetaEditor remains mandatory.

    rc=0   verified on this host
    rc=77  NOT verified on this host (no C++ compiler) - see native_toolchain
    rc=1   verified and FAILED
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import native_toolchain as NT

ROOT = Path(__file__).resolve().parents[1]
NAS = ROOT / 'MQL5/Indicators/nadir2.mq5'
TOP = ROOT / 'nadir2.mq5'

failures = []


def require(cond, message):
    if cond:
        print(f"PASS  {message}")
    else:
        print(f"FAIL  {message}")
        failures.append(message)


text = NAS.read_text()
assert TOP.read_bytes() == NAS.read_bytes(), "root mirror must match the Indicators copy"
print("PASS  repo mirror nadir2.mq5 == MQL5/Indicators/nadir2.mq5")


def function(name):
    start = text.index(name + '(')
    # Skip declarations and find the actual definition.
    while ';' in text[start:text.index('{', start)]:
        start = text.index(name + '(', start + len(name))
    end = text.index('{', start)
    depth = 1
    i = end + 1
    while depth:
        depth += (text[i] == '{') - (text[i] == '}')
        i += 1
    return text[start:i]


helpers = ('int ' + function('PMI_TriStateVerdict') + '\n' +
           'string ' + function('PMI_VerdictText') + '\n')

prelude = r'''
#include <string>
#include <cassert>
#include <iostream>
using std::string;
'''

tests = r'''
int main(){
   // The whole point: nothing checked, nothing claimed.
   assert(PMI_TriStateVerdict(false,0)==2);   // zero comparisons => INCONCLUSIVE
   assert(PMI_TriStateVerdict(false,1)==0);   // something verified => PASS
   assert(PMI_TriStateVerdict(false,100)==0);
   assert(PMI_TriStateVerdict(true,0)==1);    // a failure is a failure even with 0 checked
   assert(PMI_TriStateVerdict(true,7)==1);
   assert(PMI_VerdictText(0)=="PASS");
   assert(PMI_VerdictText(1)=="FAIL");
   assert(PMI_VerdictText(2)=="INCONCLUSIVE");
   std::cout<<"PASS native tri-state verdict semantics\n";
   return 0;
}
'''

cxx = NT.compiler(sanitizers=True)
if cxx is None:
    NT.skip('PMI replay audit (P0-3)', sanitizers=True)
else:
    with tempfile.TemporaryDirectory(prefix='pmi-p03-') as d:
        cpp = Path(d) / 'test.cpp'
        exe = Path(d) / 'test'
        cpp.write_text(prelude + helpers + tests)
        subprocess.run([cxx, '-std=c++17', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

# --- Source contract on the shipped text -----------------------------------

require('"Tests 1-4, 6"' not in text,
        "phantom 'Tests 1-4, 6' PASS text is gone")

report_m = re.search(r'g_pmi_replay\.last_report=StringFormat\(\s*"([^"]*)"', text)
require(report_m is not None and report_m.group(1).startswith("Overall "),
        "replay report carries an explicit Overall verdict prefix")
require(report_m is not None and "INCONCLUSIVE" not in report_m.group(1) and
        "Overall %s" in report_m.group(1),
        "Overall verdict is data-driven (PMI_VerdictText), not hardcoded")

require("PMI_TriStateVerdict(mismatch>0, compared)" in text,
        "REPAINT verdict is tri-state and gated on actual comparisons")
require("PMI_TriStateVerdict(future>0, lookahead_checked)" in text,
        "LOOKAHEAD verdict is tri-state and gated on a real check count")
require("PMI_TriStateVerdict(run_causality_bad>0, causality_checked)" in text,
        "CAUSALITY verdict is tri-state and gated on a real check count")

require("digests_stored<2)\n   {" in text.replace('\r\n', '\n') or
        "digests_stored<2)\r\n   {" in text,
        "cold-start skip is a block, no longer a silent return")
require("cold start: digests_stored=" in text,
        "cold-start last_report states WHY the audit did not run")
require("closed % every " in text and "[PMI Replay Audit] " in text,
        "cold-start WARN names the arming condition and is printed once per init")
require("if(g_pmi_replay.digests_stored<2) return;" not in text,
        "no silent cold-start early return remains")

require("[PMI SelfTest] INCONCLUSIVE - no scenarios executed" in text,
        "self-test cannot PASS on zero executed scenarios")
require("| executed=" in text and "pmi_scenarios_executed" in text,
        "self-test PASS line reports the executed scenario count")
require("scenario(s) failed" in text,
        "self-test FAIL line reports the failure ratio")
require("bool PMI_SelfTestExpect(const string name" in text and
        "int &executed)" in text,
        "PMI_SelfTestExpect counts every executed scenario")

print("NOT an MQL5 compilation, Strategy Tester run, or live-terminal test.")
sys.exit(1 if failures else NT.exit_code(failures))
