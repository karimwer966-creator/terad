//+------------------------------------------------------------------+
//|                                            KLJ_DataFeeder.mq5    |
//|  PART C, PHASE 6 - companion Expert Advisor.                      |
//|                                                                   |
//|  WHY THIS EXISTS                                                  |
//|  ----------------                                                 |
//|  WebRequest() is NOT permitted inside an indicator. That is an     |
//|  MQL5 platform restriction, not a design choice. Any external     |
//|  data (COT, retail sentiment, macro releases) must therefore be   |
//|  fetched out-of-process. This EA is that process. It writes a     |
//|  validated CSV into the COMMON folder; the indicator's            |
//|  CFileDataProvider only READS the result, from OnTimer.           |
//|                                                                   |
//|  WHAT IT DOES NOT DO                                              |
//|  ------------------                                               |
//|  - it contains NO endpoint and NO API key. Both are inputs.       |
//|    It ships disabled (InpFeedEnabled=false) for that reason.      |
//|  - it is not a general JSON parser. It understands flat JSON      |
//|    objects and CSV. Deeply nested API responses are reported as   |
//|    UNSUPPORTED_SHAPE and left out of the file rather than being   |
//|    guessed at.                                                    |
//|  - it never trades. No OrderSend anywhere in this file.           |
//|                                                                   |
//|  SETUP                                                            |
//|  -----                                                            |
//|  1. Tools > Options > Expert Advisors: tick "Allow WebRequest     |
//|     for listed URL" and add EVERY URL you configure below.        |
//|     Without this, WebRequest fails with error 4014/5202.          |
//|  2. Attach to any chart. It refreshes on a timer.                 |
//|  3. The indicator reads the output file; it needs no settings     |
//|     of its own beyond pointing at the same path.                  |
//|                                                                   |
//|  I CANNOT VERIFY FROM HERE: which API you licence, its terms,     |
//|  its cost, its rate limits or its symbol mapping. Those are       |
//|  inputs you must supply. See the PROVIDER NOTES block below.      |
//+------------------------------------------------------------------+
#property copyright "KLJ / QSMC v6.6.0"
#property version   "6.66"
#property description "Companion data feeder for the QSMC indicator. No trading."
#property strict

//=====================================================================
// PROVIDER NOTES - read before configuring anything.
//
// I have no way to confirm current pricing, licensing or rate limits
// from this environment, and I will not invent them. What I can state
// about the categories:
//
//   COT (Commitments of Traders)
//     - The CFTC publishes weekly reports free of charge. Positioning
//       is reported as of a Tuesday and released several days later;
//       the AS-OF date is therefore always in the past. This EA stores
//       that as-of date and the dashboard must display it.
//     - Commercial aggregators resell parsed/normalised COT under
//       licence. Terms and cost vary by vendor.
//   Retail sentiment
//     - Broker-derived positioning is usually published by the broker
//       or a reseller. Check whether redistribution to your own
//       machine is permitted by the terms you accept.
//   Macro releases
//     - Many national statistics agencies publish free; several
//       commercial calendars are licensed per seat.
//
// ACTION REQUIRED FROM YOU: tell me the provider and endpoint you
// intend to use, and I will shape InpMap* around its response. Until
// then this EA stays disabled and the indicator shows "NO DATA".
//=====================================================================

#include <QSMC/QSMC_DataProvider.mqh>

//--- Feed control -----------------------------------------------------
input bool    InpFeedEnabled          = false;  // MUST be true to do anything
input int     InpRefreshMinutes       = 60;     // timer period
input int     InpTimeoutMs            = 8000;   // WebRequest timeout, ms
input int     InpMaxRetries           = 3;      // per source, per cycle
input int     InpRetryBackoffSec      = 5;      // grows linearly per retry
input int     InpMinSecondsBetweenCalls = 10;   // local rate limit, per source

//--- Output -----------------------------------------------------------
input string  InpOutputFile           = "QSMC\\data_feed.csv";  // in FILE_COMMON
input bool    InpWriteStatusFile      = true;   // human-readable failure log

//--- Auth: the header is built as InpAuthHeader + InpApiKey, so the key
//--- never appears in the URL (and so never lands in a log verbatim).
input string  InpAuthHeader           = "X-API-Key: ";
input string  InpApiKey               = "";

//--- Up to three sources. Each needs a URL and a field map.
//--- Field map syntax: <response field>=<series_id>[;<response field>=<series_id>...]
//--- Example:  net=COT:XAU:NET_NONCOMM;comm=COT:XAU:COMM
input string  InpUrl1                 = "";
input string  InpMap1                 = "";
input string  InpUrl2                 = "";
input string  InpMap2                 = "";
input string  InpUrl3                 = "";
input string  InpMap3                 = "";

//--- Diagnostics ------------------------------------------------------
input bool    InpVerbose              = true;

//+------------------------------------------------------------------+
//| State. Bounded, flat, no dynamic allocation outside OnInit.       |
//+------------------------------------------------------------------+
#define MAX_FIELDS 64

struct SField
  {
   string            key;        // field name in the API response
   string            series_id;  // QSMC series id
  };

struct SSource
  {
   string            url;
   SField            fields[MAX_FIELDS];
   int               fields_n;
   datetime          last_call;
   int               failures;
   string            last_error;
  };

SSource  g_src[3];
int      g_src_n=0;
int      g_timer_count=0;
int      g_fetch_ok=0;
int      g_fetch_fail=0;
int      g_rows_written=0;
string   g_gen_errors="";

//+------------------------------------------------------------------+
//| Flat JSON parse. Returns the number of scalar fields found at     |
//| depth 1. Nested objects/arrays are SKIPPED and counted, never     |
//| approximated - guessing at a nested value would be worse than     |
//| reporting it missing.                                             |
//+------------------------------------------------------------------+
int ParseFlatJson(const string body,string &keys[],double &vals[],
                  string &strs[],int &skipped,const int cap)
  {
   int n=0; skipped=0;
   int len=StringLen(body);
   int i=0;

   //--- skip to the opening brace
   while(i<len && StringGetCharacter(body,i)!='{') i++;
   if(i>=len) return 0;
   i++;

   while(i<len && n<cap)
     {
      ushort ch=StringGetCharacter(body,i);
      if(ch=='}') break;
      if(ch!=',') { i++; continue; }
      i++;

      //--- read the key
      while(i<len && StringGetCharacter(body,i)!='"') i++;
      if(i>=len) break;
      i++;
      string key="";
      while(i<len && StringGetCharacter(body,i)!='"')
        { key+=ShortToString(StringGetCharacter(body,i)); i++; }
      i++;

      //--- skip to ':'
      while(i<len && StringGetCharacter(body,i)!=':') i++;
      if(i>=len) break;
      i++;
      while(i<len && (StringGetCharacter(body,i)==' ' ||
                      StringGetCharacter(body,i)=='\t')) i++;
      if(i>=len) break;

      ushort v=StringGetCharacter(body,i);
      if(v=='{' || v=='[')
        {
         //--- nested structure: consume it whole and report it skipped
         int depth=0;
         while(i<len)
           {
            ushort c=StringGetCharacter(body,i);
            if(c=='{' || c=='[') depth++;
            else if(c=='}' || c==']') { depth--; if(depth==0){ i++; break; } }
            i++;
           }
         skipped++;
         continue;
        }

      if(v=='"')
        {
         i++;
         string s="";
         while(i<len && StringGetCharacter(body,i)!='"')
           { s+=ShortToString(StringGetCharacter(body,i)); i++; }
         i++;
         keys[n]=key; vals[n]=0.0; strs[n]=s; n++;
        }
      else
        {
         string s="";
         while(i<len && StringGetCharacter(body,i)!=',' &&
                        StringGetCharacter(body,i)!='}' &&
                        StringGetCharacter(body,i)!='\n')
           { s+=ShortToString(StringGetCharacter(body,i)); i++; }
         StringTrimLeft(s); StringTrimRight(s);
         keys[n]=key; vals[n]=StringToDouble(s); strs[n]=""; n++;
        }
     }
   return n;
  }

//+------------------------------------------------------------------+
//| Parse a "a=ID;b=ID" field map.                                    |
//+------------------------------------------------------------------+
int ParseMap(const string map,SField &out[],const int cap)
  {
   int n=0;
   int len=StringLen(map);
   int start=0;
   for(int i=0;i<=len;i++)
     {
      bool at_end=(i==len);
      if(at_end || StringGetCharacter(map,i)==';')
        {
         string piece=StringSubstr(map,start,i-start);
         StringTrimLeft(piece); StringTrimRight(piece);
         int eq=StringFind(piece,"=");
         if(eq>0 && n<cap)
           {
            out[n].key=StringSubstr(piece,0,eq);
            out[n].series_id=StringSubstr(piece,eq+1);
            StringTrimLeft(out[n].key); StringTrimRight(out[n].key);
            StringTrimLeft(out[n].series_id); StringTrimRight(out[n].series_id);
            n++;
           }
         start=i+1;
        }
     }
   return n;
  }

//+------------------------------------------------------------------+
//| Fetch one source. Returns the row text appended to `rows`, or an  |
//| empty string plus an entry in g_gen_errors.                       |
//+------------------------------------------------------------------+
bool FetchSource(SSource &src,string &rows)
  {
   rows="";
   if(src.url=="" || src.fields_n==0) return false;

   //--- local rate limit: never hammer a provider, and never on the
   //--- first run.
   if(src.last_call>0)
     {
      long since=(long)TimeCurrent()-(long)src.last_call;
      if(since<InpMinSecondsBetweenCalls)
        {
         src.last_error="rate limited locally";
         return false;
        }
     }

   string headers=InpAuthHeader+InpApiKey+"\r\n";
   char   data[];
   char   result[];
   string result_headers="";
   ArrayResize(data,0);
   ArrayResize(result,0);

   int code=-1;
   int attempt=0;
   while(attempt<InpMaxRetries)
     {
      attempt++;
      code=WebRequest("GET",src.url,headers,InpTimeoutMs,data,
                      result,result_headers);
      src.last_call=TimeCurrent();
      if(code==200) break;
      if(code==-1)
        src.last_error=StringFormat("WebRequest failed, last error %d",
                                    GetLastError());
      else
        src.last_error=StringFormat("HTTP %d",code);
      if(attempt<InpMaxRetries) Sleep(InpRetryBackoffSec*1000*attempt);
     }

   if(code!=200)
     {
      src.failures++;
      g_fetch_fail++;
      return false;
     }

   string body=CharArrayToString(result,0,WHOLE_ARRAY,CP_UTF8);
   if(body=="")
     { src.last_error="empty response body"; src.failures++; return false; }

   string keys[]; double vals[]; string strs[]; int skipped=0;
   ArrayResize(keys,MAX_FIELDS); ArrayResize(vals,MAX_FIELDS);
   ArrayResize(strs,MAX_FIELDS);
   int found=ParseFlatJson(body,keys,vals,strs,skipped,MAX_FIELDS);

   if(skipped>0)
     g_gen_errors+=" ["+src.url+": "+IntegerToString(skipped)+
                   " nested field(s) skipped - UNSUPPORTED_SHAPE]";

   //--- Emit one row per mapped field that was actually present.
   int wrote=0;
   for(int f=0;f<src.fields_n;f++)
     {
      string sid=src.fields[f].series_id;
      string wanted=src.fields[f].key;
      for(int k=0;k<found;k++)
        {
         if(keys[k]!=wanted) continue;
         double v=vals[k];
         //--- A string value is stored only if it parses as a number;
         //--- otherwise the row is dropped rather than coerced to 0.
         if(strs[k]!="")
           {
            double parsed=StringToDouble(strs[k]);
            if(parsed==0.0 && strs[k]!="0" && strs[k]!="0.0") break;
            v=parsed;
           }
         //--- as_of is the provider's own stamp when it gives one,
         //--- otherwise the fetch time is recorded as the FILE time in
         //--- _meta - it is never presented as the observation date.
         rows+=StringFormat("%s,%s,%.8f,0,%s\n",sid,
                            TimeToString(TimeCurrent(),TIME_DATE|TIME_MINUTES),
                            v,wanted);
         wrote++;
         break;
        }
     }

   if(wrote==0)
     {
      src.last_error="no mapped field present in the response";
      src.failures++;
      g_fetch_fail++;
      return false;
     }

   g_fetch_ok++;
   g_rows_written+=wrote;
   return true;
  }

//+------------------------------------------------------------------+
//| Last directory separator in a path, or -1.                        |
//|                                                                   |
//| MQL5 has no StringFindRev(): a reverse search does not exist in   |
//| the language, and the compiler reports it as an undeclared        |
//| identifier, then loses the rest of the line ("',' - unexpected    |
//| token"). Scanning backwards is three lines and accepts both        |
//| separators, because the input is a path typed by a human.          |
//+------------------------------------------------------------------+
int FindLastSeparator(const string path)
  {
   for(int i=StringLen(path)-1;i>=0;i--)
     {
      ushort c=StringGetCharacter(path,i);
      if(c=='\\' || c=='/') return i;
     }
   return -1;
  }

//+------------------------------------------------------------------+
//| Atomic write: build the whole file under a .tmp name, then move   |
//| it over the target. A reader therefore sees either the old file   |
//| or the complete new one, never a half-written one.                |
//+------------------------------------------------------------------+
bool WriteFeed(const string rows)
  {
   int common=FILE_COMMON;
   string tmp=InpOutputFile+".tmp";

   //--- make sure the target directory exists
   int slash=FindLastSeparator(InpOutputFile);
   if(slash>0)
     {
      string dir=StringSubstr(InpOutputFile,0,slash);
      FolderCreate(dir,common);   // returns false if it already exists
     }

   //--- FILE_TXT: the rows are composed here with explicit CRLF, so the
   //--- CSV field handling of FILE_CSV would only get in the way.
   int h=FileOpen(tmp,FILE_WRITE|FILE_TXT|FILE_ANSI|common);
   if(h==INVALID_HANDLE)
     { g_gen_errors+=" [cannot open "+tmp+" for writing]"; return false; }

   FileWriteString(h,"# QSMC-DATA v1\r\n");
   FileWriteString(h,"series_id,as_of,value,prev,label\r\n");
   FileWriteString(h,StringFormat("_meta,%s,0,0,generated\r\n",
                   TimeToString(TimeCurrent(),TIME_DATE|TIME_MINUTES)));
   FileWriteString(h,rows);
   FileClose(h);

   //--- FileMove() takes FOUR arguments in MQL5:
   //---   (source, source_location, destination, destination_flags).
   //--- The three-argument form used here before does not exist.
   //--- FILE_COMMON appears twice because BOTH files are in the shared
   //--- folder, and FILE_REWRITE lets the rename replace the target in one
   //--- step - so the reader never sees a moment with no file at all
   //--- (the FileDelete() that used to sit here created exactly that gap).
   if(!FileMove(tmp,common,InpOutputFile,common|FILE_REWRITE))
     { g_gen_errors+=" [rename "+tmp+" -> "+InpOutputFile+" failed]";
       return false; }
   return true;
  }

//+------------------------------------------------------------------+
//| Human-readable status, so a failure is visible without the Experts|
//| tab. The indicator does NOT read this file.                       |
//+------------------------------------------------------------------+
void WriteStatus()
  {
   if(!InpWriteStatusFile) return;
   string p=InpOutputFile+".status";
   int h=FileOpen(p,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE) return;
   FileWriteString(h,"KLJ_DataFeeder status\r\n");
   FileWriteString(h,StringFormat("generated %s\r\n",
                   TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)));
   FileWriteString(h,StringFormat("cycles %d  ok %d  failed %d  rows %d\r\n",
                   g_timer_count,g_fetch_ok,g_fetch_fail,g_rows_written));
   for(int i=0;i<g_src_n;i++)
     FileWriteString(h,StringFormat("source %d failures %d last_error %s\r\n",
                     i+1,g_src[i].failures,
                     (g_src[i].last_error==""?"none":g_src[i].last_error)));
   if(g_gen_errors!="")
     FileWriteString(h,"errors: "+g_gen_errors+"\r\n");
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| One refresh cycle over every configured source.                   |
//+------------------------------------------------------------------+
void RefreshAll()
  {
   g_timer_count++;
   g_gen_errors="";
   string all="";

   for(int i=0;i<g_src_n;i++)
     {
      string rows="";
      if(FetchSource(g_src[i],rows))
        all+=rows;
      else if(InpVerbose)
        Print("[KLJ_FEED] source ",i+1," failed: ",g_src[i].last_error);
     }

   if(all!="")
     {
      if(!WriteFeed(all))
        Print("[KLJ_FEED] write failed",g_gen_errors);
      else if(InpVerbose)
        Print("[KLJ_FEED] wrote ",g_rows_written," rows -> ",InpOutputFile);
     }
   else if(InpVerbose)
     { Print("[KLJ_FEED] no rows this cycle; output left untouched"); }

   WriteStatus();
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   g_src_n=0; g_timer_count=0; g_fetch_ok=0; g_fetch_fail=0;
   g_rows_written=0;

   string urls[3];  urls[0]=InpUrl1;  urls[1]=InpUrl2;  urls[2]=InpUrl3;
   string maps[3];  maps[0]=InpMap1;  maps[1]=InpMap2;  maps[2]=InpMap3;

   for(int i=0;i<3;i++)
     {
      if(urls[i]=="" || maps[i]=="") continue;
      g_src[g_src_n].url=urls[i];
      g_src[g_src_n].fields_n=ParseMap(maps[i],g_src[g_src_n].fields,MAX_FIELDS);
      g_src[g_src_n].last_call=0;
      g_src[g_src_n].failures=0;
      g_src[g_src_n].last_error="";
      if(g_src[g_src_n].fields_n==0)
        { Print("[KLJ_FEED] source ",i+1," has an unparseable field map");
          continue; }
      g_src_n++;
     }

   if(!InpFeedEnabled)
     {
      Print("[KLJ_FEED] DISABLED (InpFeedEnabled=false). No URL is ");
      Print("[KLJ_FEED] configured in this file by design. Add the URL ");
      Print("[KLJ_FEED] to Tools > Options > Expert Advisors first.");
      return(INIT_SUCCEEDED);
     }
   if(g_src_n==0)
     {
      Print("[KLJ_FEED] enabled but no source configured: set InpUrl1 and ");
      Print("[KLJ_FEED] InpMap1. Nothing will be fetched.");
      return(INIT_SUCCEEDED);
     }
   if(InpApiKey!="" && InpAuthHeader=="")
     Print("[KLJ_FEED] WARNING: a key is set but InpAuthHeader is empty.");

   //--- MathMax() returns double; EventSetTimer() takes int seconds.
   //--- Without the cast this is the file's "possible loss of data" warning.
   EventSetTimer((int)MathMax(1,InpRefreshMinutes)*60);
   Print("[KLJ_FEED] started with ",g_src_n," source(s), period ",
         InpRefreshMinutes," min");
   RefreshAll();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Print("[KLJ_FEED] stopped. cycles=",g_timer_count," ok=",g_fetch_ok,
         " failed=",g_fetch_fail," rows=",g_rows_written);
  }

void OnTimer() { RefreshAll(); }

void OnTick() { }
//+------------------------------------------------------------------+
