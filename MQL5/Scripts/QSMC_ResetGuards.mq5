//+------------------------------------------------------------------+
//|                                          QSMC_ResetGuards.mq5    |
//|                                                                  |
//| OPERATOR TOOL - not part of the trading stack.                    |
//|                                                                  |
//| Clears the PERSISTED breaker state that QSMC_AutoTrader writes to |
//| terminal global variables, after a conscious review:              |
//|                                                                  |
//|   QSMC_AT_DAY_<login>_<magic>_<symbol>_{DAY,EQ,BLOCKED,TRADES}    |
//|   QSMC_AT_SESS_<login>_<magic>_<symbol>_{EQ,DDB,LSB,CL}           |
//|                                                                  |
//| WHY: the day guard freezes an equity baseline the first time it   |
//| sees a server day and restores it - including BLOCKED - on every  |
//| reload. If that baseline was captured at a different account      |
//| state, its floor can sit ABOVE current equity, so the guard trips |
//| on the first tick of every re-attach and no trade is ever opened. |
//| The 2026-11-06 XAUUSD journal shows exactly that:                 |
//|   day_base=5680.64 | eq~4999 | cap 0.50% -> floor 5652.24         |
//|                                                                  |
//| This tool prefers an auditable, reversible action over flipping   |
//| InpResetBreakersAtInit on a live account: that input must be set  |
//| back to false afterwards, and forgetting to do so silently        |
//| disarms the guard at the next re-attach. This script deletes      |
//| exactly the keys it lists, once, and leaves a log line for each.  |
//|                                                                  |
//| It NEVER sends an order: it links no trading function at all.     |
//|                                                                  |
//| USE: attach to the SAME symbol chart as the EA, F7, run.          |
//|      1) InpApply=false (default): prints what would be deleted.   |
//|      2) Read the list. If it names the right account/magic/symbol,|
//|         set InpApply=true and run again.                          |
//|      3) Re-attach QSMC_AutoTrader; expect                         |
//|         "[QSMC_AT] day guard: new baseline <equity>" and ARMED.   |
//+------------------------------------------------------------------+
#property copyright "QSMC"
#property version   "1.00"
#property strict
#property script_show_inputs

input bool   InpApply        = false;  // FALSE = dry run (list only). TRUE = delete the listed keys
input int    InpMagicFilter  = 0;      // only touch keys of this magic; 0 = every magic of this account+symbol
input string InpSymbolFilter = "";     // only touch keys of this symbol ("" = the chart symbol)
input bool   InpDropSession  = true;   // also clear the session guard (EQ/DDB/LSB/CL); false = day guard only

// The only two prefixes this tool knows. Anything else is left alone.
#define DAY_PREFIX  "QSMC_AT_DAY"
#define SESS_PREFIX "QSMC_AT_SESS"

//+------------------------------------------------------------------+
//| Parse QSMC_AT_<DAY|SESS>_<login>_<magic>_<symbol>_<leaf>.          |
//| Field order is fixed by DayGuardKey()/SessionGuardKey(), so the    |
//| symbol is everything between the magic and the leaf - that keeps   |
//| a suffixed symbol (XAUUSD.m, XAUUSDm) from matching XAUUSD.        |
//+------------------------------------------------------------------+
bool ParseKey(const string name,string &scope,string &login,string &magic,
              string &symbol,string &leaf)
  {
   scope=""; login=""; magic=""; symbol=""; leaf="";
   string parts[];
   int n=StringSplit(name,'_',parts);
   if(n<6) return false;
   if(parts[0]!="QSMC" || parts[1]!="AT") return false;
   if(parts[2]!="DAY" && parts[2]!="SESS") return false;
   scope=parts[2];
   login=parts[3];
   magic=parts[4];
   leaf=parts[n-1];
   symbol=parts[5];
   for(int i=6;i<n-1;i++) symbol+="_"+parts[i];
   return (symbol!="" && leaf!="");
  }

void OnStart()
  {
   string want_sym=(InpSymbolFilter=="" ? _Symbol : InpSymbolFilter);
   string want_login=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));

   // Collect first, act second: the list printed in a dry run is the exact list
   // a real run deletes.
   string hits[];
   ArrayResize(hits,0,16);
   int total=GlobalVariablesTotal();
   int other_account=0,other_symbol=0,other_scope=0;
   for(int i=0;i<total;i++)
     {
      string nm=GlobalVariableName(i);
      if(nm=="") continue;
      if(StringFind(nm,DAY_PREFIX)!=0 && StringFind(nm,SESS_PREFIX)!=0) continue;
      string scope,login,magic,sym,leaf;
      if(!ParseKey(nm,scope,login,magic,sym,leaf))
        {
         other_scope++;
         continue;
        }
      if(login!=want_login){ other_account++; continue; }
      if(sym!=want_sym)     { other_symbol++;  continue; }
      if(InpMagicFilter>0 && magic!=IntegerToString(InpMagicFilter)) continue;
      if(scope=="SESS" && !InpDropSession) continue;
      int k=ArraySize(hits);
      ArrayResize(hits,k+1,16);
      hits[k]=nm;
     }

   int n=ArraySize(hits);
   Print("[QSMC_RESET] scope: login=",want_login,
         " magic=",(InpMagicFilter>0?IntegerToString(InpMagicFilter):"ANY"),
         " symbol=",want_sym,
         " | session keys ",(InpDropSession?"INCLUDED":"excluded"),
         " | terminal globals total=",IntegerToString(total),
         " matching=",IntegerToString(n),
         " skipped[other account=",IntegerToString(other_account),
         " other symbol=",IntegerToString(other_symbol),
         " unparsed=",IntegerToString(other_scope),"]");
   if(n<=0)
     {
      Print("[QSMC_RESET] nothing to delete. The guard state is already absent for this ",
            "scope; the EA captures a fresh baseline at the next attach.");
      return;
     }

   for(int i=0;i<n;i++)
     {
      double v=GlobalVariableGet(hits[i]);
      datetime stamp=(datetime)GlobalVariableTime(hits[i]);
      Print("[QSMC_RESET] ",(InpApply?"DELETE ":"would delete "),hits[i],
            " | value=",DoubleToString(v,2),
            " | last written=",TimeToString(stamp,TIME_DATE|TIME_MINUTES));
     }

   if(!InpApply)
     {
      Print("[QSMC_RESET] DRY RUN: nothing was changed. Check that the list above names ",
            "the account, magic and symbol you reviewed, then re-run with InpApply=true ",
            "to delete exactly these ",IntegerToString(n)," key(s).");
      return;
     }

   int deleted=0,failed=0;
   for(int i=0;i<n;i++)
     {
      if(!GlobalVariableCheck(hits[i])) continue;
      if(GlobalVariableDel(hits[i])) deleted++;
      else
        {
         failed++;
         Print("[QSMC_RESET] FAILED to delete ",hits[i],
               " (error ",IntegerToString(GetLastError()),")");
        }
     }
   GlobalVariablesFlush();
   Print("[QSMC_RESET] DELETED=",IntegerToString(deleted),
         " FAILED=",IntegerToString(failed),
         " | remaining matching keys=",IntegerToString(n-deleted));
   Print("[QSMC_RESET] NEXT: re-attach QSMC_AutoTrader and confirm the journal shows ",
         "'[QSMC_AT] day guard: new baseline <equity>' with a baseline close to current ",
         "equity, then '[QSMC_AT] state ARMED'. Leave InpResetBreakersAtInit=false.");
  }
//+------------------------------------------------------------------+
