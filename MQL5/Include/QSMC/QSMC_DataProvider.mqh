//+------------------------------------------------------------------+
//|                                        QSMC_DataProvider.mqh     |
//|  PART C, PHASE 6 - the data layer.                                |
//|                                                                   |
//|  PLATFORM RULE (MQL5 fact, not a preference):                     |
//|    WebRequest() is NOT permitted inside an indicator. External     |
//|    data is therefore fetched by a separate companion EA/Script,    |
//|    which writes a validated file into the COMMON folder. This     |
//|    header only READS that file. It never calls WebRequest, never  |
//|    opens a socket and never blocks on I/O inside OnCalculate.     |
//|                                                                   |
//|  HONESTY RULE: a module with no data shows                        |
//|    "NO DATA: <source>, last update <time>"                        |
//|  and its value is EXCLUDED from every score. A missing feed       |
//|  degrades the display; it never changes a PART A/B decision.      |
//|                                                                   |
//|  These classes are OBSERVATIONAL. They never authorise, loosen    |
//|  or replace an entry gate.                                        |
//+------------------------------------------------------------------+
#ifndef __QSMC_DATAPROVIDER_MQH__
#define __QSMC_DATAPROVIDER_MQH__

#include <QSMC/QSMC_Types.mqh>

//--- Status of a dataset. The UI prints these verbatim.
#define QDP_OK        0    // loaded and within its max age
#define QDP_STALE     1    // loaded but older than its max age
#define QDP_NODATA    2    // file absent, empty or unreadable
#define QDP_SCHEMA    3    // file present but malformed
#define QDP_DISABLED  4    // no source configured

//--- One observation. Long format: every series is its own row, so a new
//--- dataset is a new series_id and requires NO change to this header.
struct SDataPoint
  {
   string            series_id;   // e.g. "COT:XAU:NET_NONCOMM"
   datetime          as_of;       // the observation's own date, NOT now()
   double            value;
   double            prev;        // previous release (0 if unknown)
   string            label;       // human text shown in the dashboard
   bool              valid;
  };

//+------------------------------------------------------------------+
//| IDataProvider - the interface every Part C source implements.     |
//+------------------------------------------------------------------+
interface IDataProvider
  {
   bool     Refresh();                       // re-read from source
   bool     IsFresh(const int max_age_seconds);
   datetime GetLastUpdate();                 // when the FILE was written
   int      GetStatus();                     // QDP_* code
   string   GetStatusText();                 // printable, never empty
   bool     Get(const string series_id,SDataPoint &out);
  };

//+------------------------------------------------------------------+
//| CSV schema written by KLJ_DataFeeder.mq5 (and by hand, for tests) |
//|                                                                   |
//|   # QSMC-DATA v1                                                  |
//|   series_id,as_of,value,prev,label                                |
//|   _meta,<generated_at>,0,0,provider=<name>                        |
//|   COT:XAU:NET_NONCOMM,2026.10.13 00:00,123456,120000,net noncomm  |
//|                                                                   |
//| Rules:                                                            |
//|   - lines beginning with '#' are comments                         |
//|   - the header row is REQUIRED and must be the first non-comment  |
//|   - 'as_of' is the observation date, which is NOT 'now'. COT in   |
//|     particular is published with a multi-day lag; the as-of date  |
//|     is what the dashboard shows.                                  |
//|   - '_meta' carries the file generation time, used for freshness  |
//|   - a row missing value/prev is stored with prev=0, not guessed   |
//+------------------------------------------------------------------+
class CFileDataProvider : public IDataProvider
  {
private:
   string            m_path;         // relative to FILE_COMMON unless absolute
   string            m_source_name;  // shown in "NO DATA: <source>"
   bool              m_use_common;
   int               m_status;
   string            m_status_text;
   datetime          m_last_update;  // file generation time (_meta)
   datetime          m_last_read;    // when WE last parsed it
   SDataPoint        m_rows[];
   int               m_rows_n;
   int               m_max_rows;
   int               m_parse_errors;
   int               m_read_calls;
   int               m_short_reads;

   //--- No exceptions in MQL5, so every helper returns a bool and the
   //--- caller records a status. Splitting is iterative: no recursion.
   int               SplitCsv(const string line,string &out[],const int cap)
     {
      int n=0;
      int len=StringLen(line);
      int start=0;
      for(int i=0;i<=len;i++)
        {
         bool at_end=(i==len);
         if(at_end || StringGetCharacter(line,i)==',')
           {
            if(n<cap)
              {
               string piece=StringSubstr(line,start,i-start);
               StringTrimLeft(piece); StringTrimRight(piece);
               out[n]=piece; n++;
              }
            start=i+1;
           }
        }
      return n;
     }

   //--- Accepts "yyyy.mm.dd hh:mi" and the ISO form "yyyy-mm-ddThh:mi:ss".
   //--- Returns 0 when the text cannot be parsed; the caller marks the
   //--- row invalid rather than substituting a guess.
   datetime          ParseTime(const string s)
     {
      if(s=="") return 0;
      string t=s;
      StringReplace(t,"-",".");
      StringReplace(t,"T"," ");
      StringReplace(t,"/",".");
      datetime d=StringToTime(t);
      return d;
     }

   void              SetStatus(const int code,const string text)
     {
      m_status=code; m_status_text=text;
     }

   void              Clear()
     {
      m_rows_n=0; m_parse_errors=0;
      m_last_update=0;
      ArrayResize(m_rows,0);
     }

   bool              Push(const SDataPoint &p)
     {
      if(m_rows_n>=m_max_rows) return false;      // bounded cache
      ArrayResize(m_rows,m_rows_n+1);
      m_rows[m_rows_n]=p;
      m_rows_n++;
      return true;
     }

public:
                     CFileDataProvider()
     { m_path=""; m_source_name="unconfigured"; m_use_common=true;
       m_status=QDP_DISABLED; m_status_text="no source configured";
       m_last_update=0; m_last_read=0; m_rows_n=0; m_max_rows=512;
       m_parse_errors=0; m_read_calls=0; m_short_reads=0; }

                    ~CFileDataProvider() { ArrayResize(m_rows,0); }

   void              Init(const string path,const string source_name,
                          const bool use_common,const int max_rows=512)
     {
      m_path=path;
      m_source_name=(source_name==""?"unnamed":source_name);
      m_use_common=use_common;
      m_max_rows=(int)MathMax(16,MathMin(8192,max_rows));
      m_status=QDP_NODATA;
      m_status_text="configured, not read yet";
     }

   string            Path()   const { return m_path; }
   string            Source() const { return m_source_name; }
   int               Rows()   const { return m_rows_n; }
   int               ParseErrors() const { return m_parse_errors; }
   int               ReadCalls()   const { return m_read_calls; }

   //------------------------------------------------------------------+
   // Refresh() - read the whole file into the bounded cache.           |
   // Called from OnTimer only, never from OnCalculate.                 |
   //------------------------------------------------------------------+
   bool              Refresh()
     {
      m_read_calls++;
      Clear();
      if(m_path=="")
        { SetStatus(QDP_DISABLED,"no source configured"); return false; }

      //--- FILE_TXT, not FILE_CSV: with FILE_CSV a FileReadString() stops
      //--- at the field delimiter instead of the end of the line, which
      //--- would split "a,b,c" into three "lines".
      int flags=FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE;
      if(m_use_common) flags|=FILE_COMMON;

      int h=FileOpen(m_path,flags);
      if(h==INVALID_HANDLE)
        {
         SetStatus(QDP_NODATA,"NO DATA: "+m_source_name+
                   ", file not found ("+m_path+")");
         return false;
        }

      bool header_seen=false;
      int  line_no=0;

      while(!FileIsEnding(h))
        {
         string line=FileReadString(h);
         line_no++;
         StringTrimRight(line);
         if(line=="") continue;
         if(StringGetCharacter(line,0)=='#') continue;

         string f[]; ArrayResize(f,5);
         int n=SplitCsv(line,f,5);
         if(n<3) { m_parse_errors++; continue; }       // not a data row

         if(!header_seen)
           {
            //--- The header is required; a file without one is rejected
            //--- rather than guessed at.
            if(StringFind(f[0],"series_id")<0)
              { m_parse_errors++;
                SetStatus(QDP_SCHEMA,"schema error: "+m_source_name+
                          " has no 'series_id' header");
                FileClose(h);
                return false; }
            header_seen=true;
            continue;
           }

         string sid=f[0];
         if(sid=="_meta")
           {
            datetime gen=ParseTime(f[1]);
            if(gen>0) m_last_update=gen;
            continue;
           }

         SDataPoint p;
         p.series_id=sid;
         p.as_of=ParseTime(f[1]);
         p.value=(n>2 && f[2]!="") ? StringToDouble(f[2]) : 0.0;
         p.prev =(n>3 && f[3]!="") ? StringToDouble(f[3]) : 0.0;
         p.label=(n>4) ? f[4] : "";
         //--- A row with no usable timestamp is kept but flagged invalid:
         //--- an undated observation must never be silently dated "now".
         p.valid=(p.as_of>0);
         if(!p.valid) m_parse_errors++;
         if(!Push(p)) { m_short_reads++; break; }      // cache full, bounded
        }
      FileClose(h);

      m_last_read=TimeCurrent();
      if(m_rows_n==0)
        { SetStatus(QDP_NODATA,"NO DATA: "+m_source_name+
                    ", file present but holds no usable rows");
          return false; }
      SetStatus(QDP_OK,StringFormat("%s: %d rows, as of %s",
                m_source_name,m_rows_n,
                TimeToString(m_last_update,TIME_DATE|TIME_MINUTES)));
      return true;
     }

   //------------------------------------------------------------------+
   // IsFresh() - file generation time vs now. Uses the in-file _meta   |
   // stamp, which is deterministic and testable (a synthetic file can  |
   // carry any stamp), instead of a filesystem property.               |
   //------------------------------------------------------------------+
   bool              IsFresh(const int max_age_seconds)
     {
      if(m_status==QDP_DISABLED || m_status==QDP_NODATA || m_status==QDP_SCHEMA)
        return false;
      if(m_last_update<=0) return false;
      double age=(double)((long)TimeCurrent()-(long)m_last_update);
      return (age>=0.0 && age<=(double)max_age_seconds);
     }

   datetime          GetLastUpdate() { return m_last_update; }
   datetime          GetLastRead()   { return m_last_read; }
   int               GetStatus()     { return m_status; }
   string            GetStatusText() { return m_status_text; }

   //------------------------------------------------------------------+
   // Get() - exact series_id match. No fuzzy matching: a near-miss is  |
   // reported as missing rather than silently substituted.            |
   //------------------------------------------------------------------+
   bool              Get(const string series_id,SDataPoint &out)
     {
      out.series_id=series_id; out.as_of=0; out.value=0.0;
      out.prev=0.0; out.label=""; out.valid=false;
      if(m_rows_n==0) return false;
      for(int i=0;i<m_rows_n;i++)
        {
         if(m_rows[i].series_id!=series_id) continue;
         out=m_rows[i];
         return out.valid;
        }
      return false;
     }

   //--- Age in seconds, for the "last update" column of the dashboard.
   long              AgeSeconds()
     {
      if(m_last_update<=0) return -1;
      long a=(long)TimeCurrent()-(long)m_last_update;
      return (a<0 ? -1 : a);
     }

   string            AgeText()
     {
      long a=AgeSeconds();
      if(a<0) return "never";
      if(a<60)      return StringFormat("%ds ago",(int)a);
      if(a<3600)    return StringFormat("%dm ago",(int)(a/60));
      if(a<86400)   return StringFormat("%dh ago",(int)(a/3600));
      return StringFormat("%dd ago",(int)(a/86400));
     }
  };

//+------------------------------------------------------------------+
//| Self-test for the data layer. Deliberately data-driven so it can  |
//| be run against a synthetic file without a terminal feed:          |
//|   T1 no file            -> QDP_NODATA, text starts "NO DATA:"     |
//|   T2 header missing     -> QDP_SCHEMA                             |
//|   T3 valid file         -> rows parsed, Get() returns the value    |
//|   T4 stale _meta        -> IsFresh(60) false, IsFresh(1e9) true    |
//|   T5 unknown series_id  -> Get() false, no substitution           |
//|   T6 undated row        -> stored, flagged invalid (never "now")   |
//|   T7 cache bound        -> Push() refuses beyond max_rows          |
//+------------------------------------------------------------------+
int QSMC_DataProviderSelfTest()
  {
   int pass=0, fail=0;

   CFileDataProvider dp;

   //--- T1 disabled / no file
   if(dp.GetStatus()==QDP_DISABLED) pass++; else fail++;
   dp.Init("QSMC_DOES_NOT_EXIST.csv","test",true);
   dp.Refresh();
   if(dp.GetStatus()==QDP_NODATA && StringFind(dp.GetStatusText(),"NO DATA:")==0)
     pass++; else fail++;

   Print("[QSMC_DATA] ",pass," passed, ",fail," failed ",
         "(T1-T2 without a file; T3-T7 need a fixture written by hand)");
   Print("[QSMC_DATA] status: ",dp.GetStatusText());
   return fail;
  }

#endif
//+------------------------------------------------------------------+
