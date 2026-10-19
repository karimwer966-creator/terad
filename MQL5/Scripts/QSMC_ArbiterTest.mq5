//+------------------------------------------------------------------+
//|                                         QSMC_ArbiterTest.mq5     |
//|  Offline harness for the v6.6.0 signal-arbitration layer.         |
//|                                                                   |
//|  HOW TO RUN                                                       |
//|   1. Copy this folder tree into your MT5 data folder:             |
//|        MQL5/Include/QSMC/*.mqh      (from repo MQL5/Include/QSMC) |
//|        MQL5/Scripts/QSMC_ArbiterTest.mq5                          |
//|   2. In MetaEditor press F7 (compile). THEN run it:               |
//|        Navigator -> Scripts -> QSMC_ArbiterTest -> drag on chart  |
//|      (or double-click; a Script has no chart dependency).         |
//|   3. Read the Experts tab. It prints one PASS/FAIL line per       |
//|      assertion and a final "RESULT: n passed, m failed".          |
//|                                                                   |
//|  WHAT IT PROVES                                                   |
//|   The ten deterministic scenarios of docs/KLJ_V6.6.0_SIGNAL_      |
//|   ARBITRATION.md section 8. They exercise the SAME code path the  |
//|   indicator runs (CQuantumRoot -> CReactionDetector -> gates ->   |
//|   CSignalArbiter -> CAlertManager) with synthetic bars, so the    |
//|   result does not depend on the symbol, the broker or the time.   |
//|                                                                   |
//|  WHAT IT CANNOT PROVE                                             |
//|   It cannot prove that MetaEditor compiles the indicator, that    |
//|   the ZRE zone list is fed correctly, or that two real charts of  |
//|   one symbol share the GlobalVariable claim. Those need F7 and a  |
//|   live terminal.                                                  |
//|                                                                   |
//|  This script places NO orders, opens NO files (CSV logging is     |
//|  off) and writes NO chart objects.                                |
//+------------------------------------------------------------------+
#property script_show_inputs
#property version   "6.63"
#property strict

#include <QSMC/QSMC_Selftest.mqh>

//--- Run on start. No OnTimer, no chart event handling.
input bool   InpRunOnStart = true;      // run the suite immediately
input bool   InpDumpLines  = false;     // re-print every assertion at the end

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
  {
   Print("=========================================================");
   Print(" QSMC_ArbiterTest - v6.6.0 signal arbitration harness");
   Print(" symbol ",_Symbol,"  tf ",QSMC_TFName((ENUM_TIMEFRAMES)_Period),
         "  point ",DoubleToString(_Point,_Digits),
         "  tick ",DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),_Digits));
   Print("=========================================================");

   if(!InpRunOnStart)
     {
      Print("InpRunOnStart=false: nothing was executed.");
      return;
     }

   int failed=QSMC_RunSelfTest();

   Print("=========================================================");
   if(failed==0)
      Print(" ALL ASSERTIONS PASSED");
   else
      Print(" ",failed," ASSERTION(S) FAILED - see the FAIL lines above");
   Print("=========================================================");
  }
//+------------------------------------------------------------------+
