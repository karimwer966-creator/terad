#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structural verifier for MQL5/Experts/QuantumAutonomousTradingSystem.mq5.

This is NOT a MetaEditor compile. It cannot replace F7. What it does is
catch the mistake classes that show up when writing a large MQL5 file by
hand, and it enforces the project's hard safety invariants:

  1. brace/paren/bracket balance (comments and strings stripped)
  2. every Inp* identifier referenced is declared as an input, exactly once
  3. every g_* global referenced is declared
  4. no duplicate definitions (inputs, globals, functions)
  5. every user-defined function called exists (native APIs are allow-listed)
  6. required lifecycle functions present: OnInit/OnDeinit/OnTick
  7. MANDATORY protection markers present: ACCOUNT_TRADE_MODE_DEMO refusal,
     terminal/EA/symbol permission checks, demo-only stance, no ML/DLL refs
  8. no forbidden MQL4 constructs (this is an MQL5 project)
  9. single-file rule: no local #include other than Trade/Trade.mqh

Usage:  python3 tools/verify_quantum_ea.py [path-to-mq5]
Exit code 0 = all checks pass. Exit code 1 = at least one failure.
"""
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "MQL5/Experts/QuantumAutonomousTradingSystem.mq5"
src = open(PATH, "r", encoding="utf-8", errors="replace").read()
orig = src
errors = []
warnings = []

def strip_comments_strings(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == '/' and nxt == '/':
            while i < n and text[i] != '\n':
                i += 1
            out.append('\n')
            continue
        if c == '/' and nxt == '*':
            depth = 1
            i += 2
            while i < n and depth:
                if text[i] == '/' and text[i + 1] == '*':
                    pass
                if text[i:i + 2] == '/*':
                    depth += 1; i += 2; continue
                if text[i:i + 2] == '*/':
                    depth -= 1; i += 2; continue
                i += 1
            continue
        if c == '"':
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2; continue
                if text[i] == '"':
                    i += 1; break
                i += 1
            out.append('""')
            continue
        if c == "'":  # char literal
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2; continue
                if text[i] == "'":
                    i += 1; break
                i += 1
            out.append("''")
            continue
        out.append(c)
        i += 1
    return "".join(out)

code = strip_comments_strings(src)

# --- 1. balance --------------------------------------------------------
pairs = {'(': ')', '[': ']', '{': '}'}
stack = []
for idx, ch in enumerate(code):
    if ch in pairs:
        stack.append((ch, idx))
    elif ch in pairs.values():
        if not stack:
            errors.append(f"unmatched closing '{ch}' at offset {idx}")
            break
        open_ch, _ = stack.pop()
        if pairs[open_ch] != ch:
            errors.append(f"mismatched '{open_ch}' vs '{ch}' at offset {idx}")
            break
for ch, idx in stack:
    errors.append(f"unclosed '{ch}' opened at offset {idx}")

# --- 9. includes --------------------------------------------------------
includes = re.findall(r'#include\s+[<"]([^>"]+)[>"]', src)
allowed_includes = {'Trade/Trade.mqh'}
for inc in includes:
    if inc not in allowed_includes:
        errors.append(f"forbidden #include <{inc}> - single-file rule violated")

# --- 2. inputs -----------------------------------------------------------
input_decls = re.findall(r'^\s*input\s+[\w\s,]*?\b(Inp\w+)\s*=', src, re.M)
input_decls = [m for m in re.findall(r'input\s+[^;\n]*?\b(Inp\w+)\s*=', src)]
seen = {}
for m in input_decls:
    seen[m] = seen.get(m, 0) + 1
for name, count in seen.items():
    if count > 1:
        errors.append(f"input '{name}' declared {count} times")
declared_inputs = set(seen)
used_inputs = set(re.findall(r'\b(Inp\w+)\b', code))
for name in sorted(used_inputs - declared_inputs):
    errors.append(f"input '{name}' used but never declared")

# --- 3. globals -----------------------------------------------------------
global_decls = []
for m in re.finditer(r'^(?:int|double|bool|datetime|string|ulong|long|uint|float|SSymbolSpec|CTrade)\b([^;{]*)', src, re.M):
    for name in re.findall(r'\b(g_\w+)\b', m.group(1)):
        global_decls.append(name)
gseen = {}
for m in global_decls:
    gseen[m] = gseen.get(m, 0) + 1
for name, count in gseen.items():
    if count > 1:
        errors.append(f"global '{name}' declared {count} times")
declared_globals = set(gseen)
used_globals = set(re.findall(r'\b(g_\w+)\b', code))
for name in sorted(used_globals - declared_globals):
    errors.append(f"global '{name}' used but never declared")

# --- 4/5. functions --------------------------------------------------------
func_defs = re.findall(r'^(?:int|double|bool|void|long|ulong|datetime|string|SAnalysis|SReading|SSymbolSpec|SZone|SSwing|SLiquidityPool)\s*\n?\s*\*?\s*(\w+)\s*\(', code, re.M)
func_defs += re.findall(r'^\s*(?:static\s+)?(?:int|double|bool|void|long|ulong|datetime|string)\s+(\w+)\s*\(', code, re.M)
func_names = set(func_defs)
NATIVE = set("""
if else for while switch return sizeof
StringFormat StringLen StringSubstr StringConcatenate IntegerToString DoubleToString StringToInteger StringToDouble
MathAbs MathFloor MathCeil MathRound MathMin MathMax MathSqrt MathPow MathLog MathExp MathMod MathIsValidNumber
ArraySize ArrayResize ArrayInitialize ArrayCopy ArrayFree ArrayMaximum ArrayMinimum
TimeCurrent TimeTradeServer TimeLocal TimeToStruct StructToTime TimeToString TIME_DATE TIME_MINUTES TIME_SECONDS
iOpen iHigh iLow iClose iVolume iTime iBars iBarShift iHighest iLowest
iMA iATR iRSI iStochastic iMACD iBands iCustom iAC iADX iBearsPower iBullsPower
CopyBuffer CopyRates CopyTime CopyOpen CopyHigh CopyLow CopyClose CopyTickVolume
IndicatorRelease IndicatorSetInteger IndicatorSetDouble
AccountInfoDouble AccountInfoInteger AccountInfoString
SymbolInfoDouble SymbolInfoInteger SymbolInfoString SymbolSelect SymbolName
TerminalInfoInteger TerminalInfoDouble MQLInfoInteger
OrderSend OrderCalcMargin OrderCalcProfit
PositionsTotal PositionSelect PositionSelectByTicket PositionGetTicket PositionGetDouble PositionGetInteger PositionGetString
HistorySelect HistoryDealsTotal HistoryDealGetTicket HistoryDealGetDouble HistoryDealGetInteger HistoryDealGetString HistoryDealSelect HistoryOrdersTotal
GlobalVariableCheck GlobalVariableGet GlobalVariableSet GlobalVariableDel
Print PrintFormat Comment
SetLevelValue
TRADE_RETCODE_DONE TRADE_RETCODE_DONE_PARTIAL TRADE_RETCODE_PLACED IsStopped
ResetLastError GetLastError
""".split())
calls = set(re.findall(r'\b([A-Za-z_]\w*)\s*\(', code))
unknown = calls - func_names - NATIVE
# CTrade methods and framework functions appear as obj.Method(...): allowed
for name in sorted(unknown):
    # ignore things that are actually method calls on an object
    if re.search(r'\.\s*' + re.escape(name) + r'\s*\(', code):
        continue
    warnings.append(f"call to '{name}(' not resolved to a user function or allow-listed native (review)")

# --- duplicate function definitions ----------------------------------------
fn_count = {}
for m in re.finditer(r'^\s*(?:static\s+)?(?:int|double|bool|void|long|ulong|datetime|string|SAnalysis|SReading|SSymbolSpec|SZone|SSwing|SLiquidityPool)\s+(\w+)\s*\(', code, re.M):
    fn_count[m.group(1)] = fn_count.get(m.group(1), 0) + 1
for name, count in fn_count.items():
    if count > 1:
        errors.append(f"function '{name}' defined {count} times")

# --- MQL5 dialect regressions reported by MetaEditor ----------------------
# Static member methods are valid, but free-standing functions cannot be static.
for m in re.finditer(r'\bstatic\s+\w+\s+\w+\s*\([^;{}]*\)\s*\{', code):
    prefix = code[:m.start()]
    if prefix.count('{') == prefix.count('}'):
        errors.append("global function cannot be declared static")

# SYMBOL_VOLUME_LIMIT is a double-valued property, not an integer enum.
if re.search(r'\bSymbolInfoInteger\s*\(\s*[^,]+,\s*SYMBOL_VOLUME_LIMIT\b', code):
    errors.append("SYMBOL_VOLUME_LIMIT must be read with SymbolInfoDouble")
if not re.search(r'\bdouble\s+volLimit\s*;', code):
    errors.append("volLimit must retain fractional lots as a double")

# --- 6/7. required lifecycle + mandatory protection markers ----------------
for needle in ["int OnInit()", "void OnDeinit(", "void OnTick()"]:
    if needle not in code:
        errors.append(f"required lifecycle function missing: {needle}")
for marker in ["ACCOUNT_TRADE_MODE_DEMO", "ACCOUNT_TRADE_MODE_REAL", "ACCOUNT_TRADE_MODE_CONTEST",
               "TERMINAL_TRADE_ALLOWED", "MQL_TRADE_ALLOWED", "SYMBOL_TRADE_MODE_FULL",
               "CTrade", "PositionModify", "InpDemoOnly", "TRADE_RETCODE_DONE"]:
    if marker not in code:
        errors.append(f"MANDATORY protection marker missing: {marker}")

# static proof the demo refusal is not decorative
if not re.search(r'mode\s*!=\s*ACCOUNT_TRADE_MODE_DEMO', code):
    errors.append("demo-mode refusal condition not found (mode != ACCOUNT_TRADE_MODE_DEMO)")
if "InpEnableTrading" not in code or "EntriesAllowed" not in code:
    errors.append("master switch / entries-allowed chain missing")

# --- 8. forbidden constructs ----------------------------------------------
for pat, why in [(r'\bstd::', 'C++ std:: forbidden'), (r'\bnew\s+\w+\[', 'MQL5 has no raw new[] arrays'),
                 (r'#property\s+strict', 'MQL4 directive, not valid MQL5'),
                 (r'\bdllimport\b', 'DLL imports forbidden'), (r'\b#import\b', 'DLL imports forbidden')]:
    if re.search(pat, code, re.I):
        errors.append(f"forbidden construct: {why}")

# --- report ----------------------------------------------------------------
print(f"verify_quantum_ea: {PATH}")
print(f"  bytes={len(orig)}  inputs={len(declared_inputs)}  globals={len(declared_globals)}  user_functions={len(func_names)}")
for w in sorted(set(warnings)):
    print(f"  WARN  {w}")
if errors:
    for e in errors:
        print(f"  FAIL  {e}")
    print(f"verify_quantum_ea: FAILED ({len(errors)} error(s))")
    sys.exit(1)
print("verify_quantum_ea: ALL CHECKS PASSED (structural only - NOT a MetaEditor compile)")
sys.exit(0)
