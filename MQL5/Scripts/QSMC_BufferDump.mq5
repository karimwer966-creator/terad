//+------------------------------------------------------------------+
//|                                              QSMC_BufferDump.mq5 |
//|                                          QSMC v6.6.24 (2026-11-16)
//|
//| R4 of the v6.6.24 audit: dump the CORE export buffers so two builds can
//| be compared on the SAME history.
//|
//| WHY
//| The executor trusts buffers 7..12 (direction, entry, SL, TP1/2/3) and reads
//| 21..25 (class, score, reliability, rr1, risk multiplier). A release that
//| claims "nothing in the signal path changed" has to be able to SHOW it: run
//| this script on the same symbol, timeframe and bar count with the old build
//| and the new one, then diff the two CSVs. docs/BUFFER_DIFF_v6.6.23_v6.6.24.md
//| says exactly what may differ and why.
//|
//| HOW
//|   1. compile nadir2.mq5, attach it to a chart ONCE (so the .ex5 exists and
//|      the terminal has history for the symbol/timeframe);
//|   2. run this script on the same chart;
//|   3. the CSV lands in MQL5/Files/.
//|   4. repeat with the other build, then:  diff -u old.csv new.csv
//|
//| This script only READS buffers. It creates no object, sends no order, and
//| touches nothing the indicator owns.
//+------------------------------------------------------------------+
#property copyright   "QSMC"
#property version     "6.624"
#property description "Dump CORE buffers 7..12 and classification buffers 21..25 to CSV for a build-to-build diff."
#property script_show_inputs
#property strict

input int    InpBars      = 200;                       // how many bars to dump (>=10)
input string InpOutFile   = "QSMC_buffers.csv";         // file in MQL5/Files
input string InpIndName   = "nadir2";                   // indicator name (compiled defaults)

//--- The ABI this script probes. Kept as literals on purpose: if the indicator
//--- ever rebinds these slots, the dump stops matching the contract and the
//--- difference shows up as a column shift instead of a silent mis-read.
#define BUF_CORE_DIR    7
#define BUF_CORE_ENTRY  8
#define BUF_CORE_SL     9
#define BUF_CORE_TP1   10
#define BUF_CORE_TP2   11
#define BUF_CORE_TP3   12
#define BUF_CLASS      21
#define BUF_SCORE      22
#define BUF_RELIAB     23
#define BUF_RR1        24
#define BUF_RISKMUL    25

void OnStart()
  {
   int bars=(int)MathMax(10,InpBars);
   int handle=iCustom(_Symbol,_Period,InpIndName);
   if(handle==INVALID_HANDLE)
     {
      Print("[QSMC_DUMP] FATAL: cannot create the ",InpIndName," handle (error ",
            IntegerToString(GetLastError()),"). Compile the indicator first.");
      return;
     }
   //--- The indicator needs one calculation pass before CopyBuffer answers.
   int waited=0;
   while(BarsCalculated(handle)<bars && waited<200)
     {
      Sleep(50);
      waited++;
     }
   int calc=BarsCalculated(handle);
   Print("[QSMC_DUMP] BarsCalculated=",IntegerToString(calc),
         " after ",IntegerToString(waited*50)," ms; dumping ",IntegerToString(bars)," bars");

   int slots[11];
   slots[0]=BUF_CORE_DIR;   slots[1]=BUF_CORE_ENTRY; slots[2]=BUF_CORE_SL;
   slots[3]=BUF_CORE_TP1;   slots[4]=BUF_CORE_TP2;   slots[5]=BUF_CORE_TP3;
   slots[6]=BUF_CLASS;      slots[7]=BUF_SCORE;      slots[8]=BUF_RELIAB;
   slots[9]=BUF_RR1;        slots[10]=BUF_RISKMUL;
   string names[11];
   names[0]="core_dir";   names[1]="core_entry"; names[2]="core_sl";
   names[3]="core_tp1";   names[4]="core_tp2";   names[5]="core_tp3";
   names[6]="class";      names[7]="score";      names[8]="reliability";
   names[9]="rr1";        names[10]="risk_mult";

   double buf[11][];
   int got[11];
   for(int s=0;s<11;s++)
     {
      ArraySetAsSeries(buf[s],false);
      got[s]=CopyBuffer(handle,slots[s],0,bars,buf[s]);
     }

   int h=FileOpen(InpOutFile,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(h==INVALID_HANDLE)
     {
      Print("[QSMC_DUMP] FATAL: cannot write ",InpOutFile," (error ",
            IntegerToString(GetLastError()),")");
      return;
     }
   FileWrite(h,"bar_time","shift_from_newest","symbol","period_minutes",
             names[0],names[1],names[2],names[3],names[4],names[5],
             names[6],names[7],names[8],names[9],names[10],
             "copied_core_dir","copied_core_entry","copied_core_sl",
             "copied_core_tp1","copied_core_tp2","copied_core_tp3",
             "copied_class","copied_score","copied_reliab","copied_rr1","copied_riskmul",
             "bars_calculated");

   //--- Bar times, read ONCE (not per row): the label of a row must be the
   //--- series' own time, so a gap in history cannot shift the labels.
   datetime times[];
   ArraySetAsSeries(times,false);
   int time_n=CopyTime(_Symbol,_Period,0,bars,times);
   datetime last_bar=(datetime)SeriesInfoInteger(_Symbol,_Period,SERIES_LASTBAR_DATE);

   int rows=0;
   for(int i=0;i<bars;i++)
     {
      datetime bt=(time_n>=bars ? times[bars-1-i] : 0);
      FileWrite(h,
                TimeToString(bt,TIME_DATE|TIME_SECONDS),
                IntegerToString(i),
                _Symbol,
                IntegerToString((int)(PeriodSeconds(_Period)/60)),
                DoubleToString((got[0]>i  ? buf[0][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[1]>i  ? buf[1][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[2]>i  ? buf[2][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[3]>i  ? buf[3][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[4]>i  ? buf[4][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[5]>i  ? buf[5][i]  : EMPTY_VALUE),_Digits),
                DoubleToString((got[6]>i  ? buf[6][i]  : EMPTY_VALUE),2),
                DoubleToString((got[7]>i  ? buf[7][i]  : EMPTY_VALUE),2),
                DoubleToString((got[8]>i  ? buf[8][i]  : EMPTY_VALUE),2),
                DoubleToString((got[9]>i  ? buf[9][i]  : EMPTY_VALUE),2),
                DoubleToString((got[10]>i ? buf[10][i] : EMPTY_VALUE),2),
                IntegerToString(got[0]),IntegerToString(got[1]),IntegerToString(got[2]),
                IntegerToString(got[3]),IntegerToString(got[4]),IntegerToString(got[5]),
                IntegerToString(got[6]),IntegerToString(got[7]),IntegerToString(got[8]),
                IntegerToString(got[9]),IntegerToString(got[10]),
                IntegerToString(calc));
      rows++;
     }
   FileFlush(h);
   FileClose(h);
   IndicatorRelease(handle);
   Print("[QSMC_DUMP] wrote ",IntegerToString(rows)," rows to ",InpOutFile,
         " | bars=",IntegerToString(bars),
         " | last bar ",TimeToString(last_bar,TIME_DATE|TIME_SECONDS));
   Print("[QSMC_DUMP] this is a READ of the indicator's buffers: no order was sent, ",
         "no object was created, and nothing in the signal path was changed.");
  }
//+------------------------------------------------------------------+
