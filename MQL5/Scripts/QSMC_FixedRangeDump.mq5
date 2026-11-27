//+------------------------------------------------------------------+
//| QSMC_FixedRangeDump.mq5                                          |
//| Diagnostic-only fixed-range dump of nadir2 buffers 0..25.         |
//|                                                                  |
//| BASELINE REFERENCE (not compiled into production binaries)        |
//| Production sources this tool must NOT be mistaken for:            |
//|   base commit 06bd0896b4a1aa18ea1d880276c1083be5a8aac2 (main)    |
//|   hashes docs/QSMC_BASELINE_HASHES.md                            |
//|   NOTE: tag pre-refactor-v6.6.24 no longer resolves on origin;    |
//|   the baseline pin is the commit hash above. Do NOT recreate it.  |
//|                                                                  |
//| IMPORTANT SIDE-EFFECT LIMITATION                                 |
//| This script itself sends no orders, creates no GlobalVariables,   |
//| chart objects, or trading state, and does not modify indicator    |
//| buffers. However, the current nadir2 source is NOT side-effect    |
//| free when created by iCustom without the EA's GV handshake:       |
//|   * OnInit scans GlobalVariablesTotal()/GlobalVariableName() for  |
//|     "QSMC_EA_READER_HANDSHAKE_*" and DELETES fresh matches        |
//|     (nadir2.mq5 ~14900-14955),                                   |
//|   * it then paints/deletes PFX-prefixed objects when it decides   |
//|     it is a VISUAL instance (non-reader role),                    |
//|   * and DiagPublishCoreState() calls GlobalVariableSet() once per |
//|     closed bar for QSMC diag keys (~20324-20354).                 |
//| This script cannot prevent those target-indicator side effects    |
//| without changing nadir2 or creating the forbidden handshake GV.   |
//| Run ONLY in a separate disposable portable MT5 installation and   |
//| on an empty disposable chart. Isolation does not make nadir2's    |
//| internal GV writes cease to occur.                                |
//|                                                                  |
//| The EA calls iCustom(_Symbol,_Period,InpIndicatorName) passing NO |
//| indicator inputs (EA lines ~3300s; compiled defaults apply).      |
//| This tool calls iCustom(symbol,PERIOD_M15,InpIndicatorName), also |
//| with NO arguments -> identical compiled-default inputs.            |
//| Equivalence limitation: identical ONLY when the EA chart symbol   |
//| equals `symbol` and the EA chart period is PERIOD_M15. This tool  |
//| forces M15; do not use it to reason about other timeframes.       |
//|                                                                  |
//| Range endpoints are EXACT M15 bar-open times in broker/server     |
//| time, inclusive. Exported bars are CLOSED bars only (shift >= 1); |
//| shift 0 (forming bar) is never exported. Timestamps in the CSV    |
//| are bar-open times; every row carries the bar it belongs to.      |
//|                                                                  |
//| This tool makes NO claim about historical CORE backfill. See      |
//| docs/QSMC_FIXED_RANGE_DUMP_RUNBOOK.md, section "Historical CORE   |
//| backfill" before interpreting an all-zero dump.                   |
//+------------------------------------------------------------------+
#property strict
#property script_show_inputs
#property version "6.625"
#property description "Diagnostic-only fixed-range closed-bar dump of nadir2 buffers 0..25"

#include <QSMC/QSMC_OpportunityFunnel.mqh>

#define QSMC_FIXED_TF       PERIOD_M15
#define QSMC_BUFFER_COUNT   26
#define QSMC_MAX_ROWS       10000

input string   InpSymbol="";                     // blank = chart symbol
input string   InpIndicatorName="nadir2";        // same indicator name; NO inputs passed (compiled defaults)
input datetime InpStart=D'2026.01.01 00:00';     // EXACT M15 bar-open time, broker/server time, inclusive
input datetime InpEnd=D'2026.01.02 00:00';       // EXACT M15 bar-open time, broker/server time, inclusive
input string   InpOutFile="QSMC_fixed_range_M15.csv"; // written under terminal-LOCAL MQL5/Files
input int      InpReadyWaitSeconds=30;           // max wait for BarsCalculated to cover the range
input bool     InpConfirmedIsolatedPortableTerminal=false; // must be true; disposable portable terminal only

//--- helpers ---------------------------------------------------------
string FixedTime(const datetime value)
  {
   return TimeToString(value,TIME_DATE|TIME_MINUTES|TIME_SECONDS);
  }

// CSV field for one raw buffer cell. Distinguishes three cases:
//   READ_FAIL     - CopyBuffer for THAT buffer on THAT bar returned != 1
//   EMPTY_VALUE   - the buffer genuinely holds the EMPTY_VALUE sentinel
//   <number>      - raw numeric value, full precision
string CsvCell(const double value,const bool read_ok)
  {
   if(!read_ok) return "READ_FAIL";
   if(value==EMPTY_VALUE) return "EMPTY_VALUE";   // sentinel comparison is exact by design
   if(!MathIsValidNumber(value)) return "INVALID_NUMBER";
   return DoubleToString(value,16);
  }

bool SameRate(const MqlRates &a,const MqlRates &b)
  {
   return (a.time==b.time && a.open==b.open && a.high==b.high &&
           a.low==b.low && a.close==b.close &&
           a.tick_volume==b.tick_volume && a.real_volume==b.real_volume &&
           a.spread==b.spread);
  }

string BufferHeader(const int index)
  {
   if(index==21) return "buffer_21_SCORE";
   if(index==22) return "buffer_22_CLASS";
   return "buffer_"+IntegerToString(index);
  }

void Fail(const string message,const int handle=INVALID_HANDLE)
  {
   Print("[QSMC_FIXED_DUMP] FATAL: ",message);
   if(handle!=INVALID_HANDLE) IndicatorRelease(handle);
  }

//--- main ------------------------------------------------------------
void OnStart()
  {
   // Phase B seam: reset the diagnostics-only opportunity-funnel module.
   // Touches only the module's own counters; changes nothing about this
   // script's output or about any production path (it is not wired there).
   QSMC_OF_Reset();
   if(!InpConfirmedIsolatedPortableTerminal)
     {
      Fail("refusing to run: set InpConfirmedIsolatedPortableTerminal=true ONLY in a separate disposable portable MT5 installation; nadir2 itself has GV/chart side effects without the EA handshake (it will read/delete QSMC_EA_READER_HANDSHAKE_* GVs, publish QSMC diag GVs once per closed bar, and draw/delete PFX objects in its default VISUAL role)");
      return;
     }
   if(InpIndicatorName=="" || InpOutFile=="")
     {
      Fail("InpIndicatorName and InpOutFile must not be empty");
      return;
     }
   if(InpStart<=0 || InpEnd<=0 || InpStart>InpEnd)
     {
      Fail("invalid range: require 0 < InpStart <= InpEnd");
      return;
     }

   string symbol=InpSymbol;
   if(symbol=="") symbol=_Symbol;
   if(!SymbolSelect(symbol,true))
     {
      Fail("SymbolSelect failed for "+symbol+" (error "+IntegerToString(GetLastError())+")");
      return;
     }

   Print("[QSMC_FIXED_DUMP] WARNING: the SCRIPT itself creates no orders/GVs/chart objects and never writes to indicator buffers; the TARGET indicator (nadir2) does write its own GVs and chart objects as described in the header. Isolated portable terminal required and accepted.");
   Print("[QSMC_FIXED_DUMP] symbol=",symbol,
         " timeframe=M15 indicator=",InpIndicatorName,
         " inputs=compiled defaults (iCustom called with no arguments, same form as the EA)");
   Print("[QSMC_FIXED_DUMP] EA equivalence holds ONLY if the EA chart symbol=='",symbol,"' and EA chart period==M15; this tool forces PERIOD_M15.");
   Print("[QSMC_FIXED_DUMP] requested server range (inclusive): ",FixedTime(InpStart)," .. ",FixedTime(InpEnd));
   long build=TerminalInfoInteger(TERMINAL_BUILD);
   Print("[QSMC_FIXED_DUMP] terminal build=",(build>0?IntegerToString((int)build):"unavailable"),
         " | login/account/server identifiers are NOT read and NOT printed");

   int bars=Bars(symbol,QSMC_FIXED_TF);
   if(bars<2)
     {
      Fail("M15 history unavailable (Bars="+IntegerToString(bars)+")");
      return;
     }
   datetime oldest=iTime(symbol,QSMC_FIXED_TF,bars-1);
   datetime newest_open=iTime(symbol,QSMC_FIXED_TF,0);
   Print("[QSMC_FIXED_DUMP] history bars=",bars," oldest_open=",FixedTime(oldest),
         " current_open=",FixedTime(newest_open),
         " synchronized=",(SeriesInfoInteger(symbol,QSMC_FIXED_TF,SERIES_SYNCHRONIZED)!=0?"yes":"no"));

   // Exact endpoint resolution. iBarShift(exact=true) returns -1 when the
   // requested timestamp is not an existing bar opening time; this rejects
   // ambiguous endpoints by construction.
   int start_shift=iBarShift(symbol,QSMC_FIXED_TF,InpStart,true);
   int end_shift=iBarShift(symbol,QSMC_FIXED_TF,InpEnd,true);
   if(start_shift<0 || end_shift<0)
     {
      Fail("range endpoint is not an exact existing M15 bar-open time; pass broker/server bar-open timestamps and ensure the history is downloaded/synchronized");
      return;
     }
   if(iTime(symbol,QSMC_FIXED_TF,start_shift)!=InpStart ||
      iTime(symbol,QSMC_FIXED_TF,end_shift)!=InpEnd)
     {
      Fail("exact endpoint verification failed; no output written");
      return;
     }
   if(start_shift<end_shift)
     {
      Fail("shift ordering inconsistent (start_shift<end_shift); check requested dates and history");
      return;
     }
   if(start_shift==0)
     {
      Fail("InpStart resolves to the FORMING bar (shift 0); the range must start on a closed M15 bar");
      return;
     }

   // shift 0 is never exported. If InpEnd resolves to shift 0 (the forming
   // bar), clamp to shift 1 and report the clamp explicitly.
   int last_closed_shift=(end_shift<1 ? 1 : end_shift);
   int rows=start_shift-last_closed_shift+1;
   if(rows<=0 || rows>QSMC_MAX_ROWS)
     {
      Fail("selected closed-bar count invalid or exceeds safety cap "+IntegerToString(QSMC_MAX_ROWS)+" (rows="+IntegerToString(rows)+")");
      return;
     }
   bool clamped=(end_shift==0 && last_closed_shift==1);
   datetime actual_first=iTime(symbol,QSMC_FIXED_TF,start_shift);      // oldest in range
   datetime actual_last =iTime(symbol,QSMC_FIXED_TF,last_closed_shift); // newest closed bar exported
   Print("[QSMC_FIXED_DUMP] actual closed-bar range: ",FixedTime(actual_first)," .. ",FixedTime(actual_last),
         " rows=",rows,(clamped?" (InpEnd was the forming bar; clamped to shift 1)":""));

   ResetLastError();
   int handle=iCustom(symbol,QSMC_FIXED_TF,InpIndicatorName); // intentionally NO input arguments
   if(handle==INVALID_HANDLE)
     {
      Fail("iCustom handle invalid for "+symbol+" M15 "+InpIndicatorName+
           " (error "+IntegerToString(GetLastError())+")");
      return;
     }

   int calculated=BarsCalculated(handle);
   int waited_ms=0;
   int ready_wait_ms=(InpReadyWaitSeconds<0 ? 0 : InpReadyWaitSeconds*1000);
   while(calculated>=0 && calculated<start_shift+1 && waited_ms<ready_wait_ms)
     {
      Sleep(100);
      waited_ms+=100;
      calculated=BarsCalculated(handle);
     }
   bool ready=(calculated>=start_shift+1);
   Print("[QSMC_FIXED_DUMP] indicator readiness BarsCalculated=",calculated,
         " required_at_least=",start_shift+1,
         " wait_ms=",waited_ms," ready=",(ready?"yes":"NO"));
   if(calculated<0)
     {
      Fail("BarsCalculated reports error; no output written",handle);
      return;
     }
   if(!ready)
      Print("[QSMC_FIXED_DUMP] WARNING: indicator did not cover the requested range within ",InpReadyWaitSeconds,"s; buffers may hold partial data for old bars. Treat old rows as READ_FAIL/incomplete, not as trading evidence.");

   //--- pass 1: snapshot bars + buffer cells, oldest -> newest -----------
   MqlRates before[];   ArrayResize(before,rows);
   double   vals[];     ArrayResize(vals,rows*QSMC_BUFFER_COUNT);
   bool     cell_ok[];  ArrayResize(cell_ok,rows*QSMC_BUFFER_COUNT);
   string   row_status[]; ArrayResize(row_status,rows);
   MqlRates snap[];     ArrayResize(snap,1);
   double   one[];      ArrayResize(one,1); ArraySetAsSeries(one,true);

   int read_errors=0,missing_bars=0,short_reads=0;
   for(int r=0;r<rows;r++)
     {
      int shift=start_shift-r;
      string status="OK";
      ZeroMemory(before[r]);
      datetime exact_time=iTime(symbol,QSMC_FIXED_TF,shift);
      int got_rates=CopyRates(symbol,QSMC_FIXED_TF,shift,1,snap);
      if(shift<1 || got_rates!=1 || exact_time<=0 || snap[0].time!=exact_time)
        {
         status="MISSING_BAR";
         missing_bars++;
         read_errors++;
         for(int b=0;b<QSMC_BUFFER_COUNT;b++){ vals[r*QSMC_BUFFER_COUNT+b]=EMPTY_VALUE; cell_ok[r*QSMC_BUFFER_COUNT+b]=false; }
         row_status[r]=status;
         Print("[QSMC_FIXED_DUMP] MISSING_BAR row=",r," shift=",shift,
               " CopyRates=",got_rates," iTime=",FixedTime(exact_time));
         continue;
        }
      before[r]=snap[0];
      if(before[r].time<InpStart || before[r].time>InpEnd) { status="OUT_OF_REQUESTED_RANGE"; read_errors++; }
      for(int b=0;b<QSMC_BUFFER_COUNT;b++)
        {
         one[0]=EMPTY_VALUE;
         ResetLastError();
         int got=CopyBuffer(handle,b,shift,1,one);
         int idx=r*QSMC_BUFFER_COUNT+b;
         if(got!=1)
           {
            vals[idx]=EMPTY_VALUE; cell_ok[idx]=false;
            status="COPY_SHORT"; short_reads++; read_errors++;
            Print("[QSMC_FIXED_DUMP] COPY_SHORT row=",r," time=",FixedTime(before[r].time),
                  " buffer=",b," requested=1 got=",got," error=",GetLastError());
           }
         else
           {
            vals[idx]=one[0]; cell_ok[idx]=true;
           }
        }
      row_status[r]=status;
     }

   //--- pass 2: did any collected bar change underneath us? --------------
   // Re-ask for the SAME timestamp (never trust shift identity across a
   // possible new-bar boundary) and compare full OHLC/volume/spread.
   int changed_bars=0;
   for(int r=0;r<rows;r++)
     {
      if(before[r].time<=0) continue;
      int now_shift=iBarShift(symbol,QSMC_FIXED_TF,before[r].time,true);
      bool changed=(now_shift<1); // no longer a closed bar at that time, or gone
      MqlRates after[]; ArrayResize(after,1);
      if(!changed)
        {
         int got=CopyRates(symbol,QSMC_FIXED_TF,now_shift,1,after);
         changed=(got!=1 || after[0].time!=before[r].time || !SameRate(before[r],after[0]));
        }
      if(changed)
        {
         row_status[r]+="|BAR_CHANGED";
         changed_bars++;
         Print("[QSMC_FIXED_DUMP] BAR_CHANGED time=",FixedTime(before[r].time),
               " old_shift=",start_shift-r," new_shift=",now_shift);
        }
     }

   //--- write CSV ---------------------------------------------------------
   string header="bar_time_server,shift_at_read,symbol,timeframe_minutes,bar_status,bars_calculated";
   for(int b=0;b<QSMC_BUFFER_COUNT;b++) header+=","+BufferHeader(b);

   int file=FileOpen(InpOutFile,FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(file==INVALID_HANDLE)
     {
      Fail("cannot write terminal-local MQL5/Files/"+InpOutFile+
           " (error "+IntegerToString(GetLastError())+")",handle);
      return;
     }
   FileWriteString(file,header+"\r\n");
   for(int r=0;r<rows;r++)
     {
      int shift=start_shift-r;
      string ts=(before[r].time>0?FixedTime(before[r].time):"MISSING");
      string line=ts+","+IntegerToString(shift)+","+symbol+",15,"+row_status[r]+","+IntegerToString(calculated);
      for(int b=0;b<QSMC_BUFFER_COUNT;b++)
         line+=","+CsvCell(vals[r*QSMC_BUFFER_COUNT+b],cell_ok[r*QSMC_BUFFER_COUNT+b]);
      FileWriteString(file,line+"\r\n");
     }
   FileClose(file);
   IndicatorRelease(handle);

   datetime current_open_after=iTime(symbol,QSMC_FIXED_TF,0);
   Print("[QSMC_FIXED_DUMP] requested=",FixedTime(InpStart),"..",FixedTime(InpEnd),
         " actual_closed=",FixedTime(actual_first),"..",FixedTime(actual_last),
         " rows=",rows," timeframe=M15 symbol=",symbol," shift0_excluded=yes");
   Print("[QSMC_FIXED_DUMP] current_bar_at_start=",FixedTime(newest_open),
         " current_bar_at_end=",FixedTime(current_open_after),
         " new_bar_during_collection=",(newest_open!=current_open_after?"yes":"no"));
   Print("[QSMC_FIXED_DUMP] row_errors=",read_errors," short_CopyBuffer_reads=",short_reads,
         " missing_bars=",missing_bars," changed_bars=",changed_bars,
         " output=MQL5/Files/",InpOutFile);
   Print("[QSMC_FIXED_DUMP] buffer labels: 21=SCORE (BufSigCoreScore, INDICATOR_CALCULATIONS), 22=CLASS (BufSigCoreClass). EMPTY_VALUE written as literal; READ_FAIL marks a failed CopyBuffer for that cell.");
   Print("[QSMC_FIXED_DUMP] REMINDER: a freshly attached nadir2 handle does NOT prove historical CORE backfill; all-zero/empty CORE cells are NOT evidence of equivalence. Historical signal equivalence is NOT VERIFIED. Use Strategy Tester forward replay per docs/QSMC_TESTER_PLAN_1_OBSERVATION.md and docs/QSMC_TESTER_PLAN_2_EXECUTION.md.");
  }
//+------------------------------------------------------------------+
