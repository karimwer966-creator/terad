#ifndef QSMC_UNIFIED_DECISION_MQH
#define QSMC_UNIFIED_DECISION_MQH
// Migration switch: legacy execution, buffer numbering and thresholds stay intact.
#ifndef QSMC_UD_NATIVE_TEST
input group "====== Unified Core authority / merged rendering ======"
input bool InpUnifiedDecision = false; // explicit opt-in; advisory layers never authorize
input double InpUnifiedMergeATR = 0.15; // same-side zone/path consolidation tolerance
input int InpMessageCooldownBars = 10; // 0 disables diagnostic dedup; 1..1000 bars
#endif
#define UD_LOG_CAP 128
struct SUnifiedDecision
{
   datetime bar;
   int direction;
   int score;
   string reasons;
};
SUnifiedDecision g_ud;

// Pure policy, also executed by the native runtime tests. Core is the authority;
// advisory opposition cannot flip, create or veto its already gated confirmation.
void UD_Policy(const int authority,const bool conflict,const bool bias,
               const bool reaction,const bool tactical,SUnifiedDecision &out)
{
   out.direction=0; out.score=0; out.reasons="WAIT: no closed-bar Core confirmation";
   if(conflict) { out.reasons="WAIT: conflicting Core confirmations"; return; }
   if(authority!=1 && authority!=-1) return;
   out.direction=authority; out.score=60;
   out.reasons="Core confirmed (60)";
   if(bias) { out.score+=10; out.reasons+="; HTF aligned (+10)"; }
   if(reaction) { out.score+=15; out.reasons+="; closed reaction aligned (+15)"; }
   if(tactical) { out.score+=15; out.reasons+="; closed tactical aligned (+15)"; }
}

void UD_Update(const int closed)
{
   g_ud.bar=0; UD_Policy(0,false,false,false,false,g_ud);
   if(closed<0 || closed>=g_rates_total-1 || closed+1>=ArraySize(g_buf_t)) return;
   int direction=0; bool conflict=false;
   datetime boundary=g_buf_t[closed+1];
   for(int i=ArraySize(g_confirmed_signal_journal)-1;i>=0;i--)
   {
      SConfirmedSignalJournalEntry e=g_confirmed_signal_journal[i];
      if(e.availability_time!=boundary || e.confirmation_bar!=closed ||
         e.confirmation_bar<=e.created_bar) continue;
      int d=(e.is_buy?1:-1);
      if(direction!=0 && direction!=d) conflict=true;
      direction=d;
   }
   bool reaction=false;
   if(g_rxn_built_time==g_buf_t[closed])
   {
      if(direction>0) reaction=g_rxn_best_buy.valid && g_rxn_best_buy.level>=(int)RXN_LEVEL_REACTION;
      if(direction<0) reaction=g_rxn_best_sell.valid && g_rxn_best_sell.level>=(int)RXN_LEVEL_REACTION;
   }
   UD_Policy(direction,conflict,InpUseHTFBias && g_htf_bias==direction && direction!=0,
             reaction,g_tac_closed && g_tac_dir==direction && direction!=0,g_ud);
   g_ud.bar=g_buf_t[closed];
}

int UD_Verdict(const int closed,string &why)
{
   if(closed<0 || closed>=ArraySize(g_buf_t) || g_ud.bar!=g_buf_t[closed])
   { g_res_score=0; why="WAIT: unified snapshot unavailable"; return 0; }
   g_res_score=g_ud.score; why=g_ud.reasons; return g_ud.direction;
}

bool UD_AlertAllows(const int source,const int direction)
{
   if(!InpUnifiedDecision || direction==0) return true;
   return source==3 && direction==g_ud.direction && g_ud.direction!=0;
}

double UD_Tolerance(const double atr)
{
   if(!MathIsValidNumber(atr) || atr<=0.0 || atr==EMPTY_VALUE) return 0.0;
   double factor=InpUnifiedMergeATR;
   if(!MathIsValidNumber(factor) || factor<0.0 || factor>1.0) factor=0.15;
   return atr*factor;
}

bool UD_Near(const double alo,const double ahi,const int aside,
             const double blo,const double bhi,const int bside,const double tol)
{
   return aside==bside && alo<=ahi && blo<=bhi &&
      MathMax(alo,blo)-MathMin(ahi,bhi)<=tol;
}

// Reconcile the retained *scored* lists, then reapply render caps, preserving the strongest
// evidence record. Touches are recounted as episodes on the union, never summed.
void UD_MergeZones(SZREZone &out[],SZREZone &dropped[],SZREZone &tail[],
                   const SZREContext &ctx,const double &h[],const double &l[])
{
   if(!InpUnifiedDecision) return;
   SZREZone all[];
   int n=ArraySize(out)+ArraySize(dropped)+ArraySize(tail);
   if(n<2 || ArrayResize(all,n)!=n) return;
   int k=0;
   for(int i=0;i<ArraySize(out);i++) all[k++]=out[i];
   for(int i=0;i<ArraySize(dropped);i++) all[k++]=dropped[i];
   for(int i=0;i<ArraySize(tail);i++) all[k++]=tail[i];
   // Canonical geometry order makes chain unions independent of input order.
   for(int i=1;i<n;i++)
   {
      SZREZone key=all[i]; int j=i-1;
      while(j>=0 && (all[j].lo>key.lo || (all[j].lo==key.lo && StringCompare(all[j].id,key.id)>0)))
      { all[j+1]=all[j]; j--; }
      all[j+1]=key;
   }
   bool changed=true;
   while(changed)
   {
      changed=false;
      for(int i=0;i<n && !changed;i++) for(int j=i+1;j<n;j++)
      {
         if(!UD_Near(all[i].lo,all[i].hi,(int)all[i].side,all[j].lo,all[j].hi,(int)all[j].side,UD_Tolerance(ctx.atr))) continue;
         double lo=MathMin(all[i].lo,all[j].lo),hi=MathMax(all[i].hi,all[j].hi);
         int age=(all[i].age_bars<0 || all[j].age_bars<0 ? -1 : (int)MathMax(all[i].age_bars,all[j].age_bars));
         string sources=ZRE_TokenUnion(all[i].sources,all[j].sources);
         if(ZRE_ZoneBefore(all[j],all[i],ctx.close_px)) all[i]=all[j];
         all[i].lo=lo; all[i].hi=hi; all[i].age_bars=age; all[i].sources=sources;
         int first=(int)MathMax(0,ctx.closed-ctx.hist);
         if(age>=0) first=(int)MathMax(first,ctx.closed-age);
         all[i].touches=ZRE_CountTouchEpisodes(lo,hi,ctx.touch_tol,first,ctx.closed-1,h,l);
         all[i].id=ZRE_ZoneId(all[i].side,lo,hi);
         all[i].detail+=" | merged union; strength from strongest constituent; touches recounted";
         for(int p=j;p<n-1;p++) all[p]=all[p+1];
         n--; changed=true; break;
      }
   }
   for(int i=1;i<n;i++)
   {
      SZREZone key=all[i]; int j=i-1;
      while(j>=0 && ZRE_ZoneBefore(key,all[j],ctx.close_px)) { all[j+1]=all[j]; j--; }
      all[j+1]=key;
   }
   ArrayResize(out,0); ArrayResize(dropped,0); ArrayResize(tail,0);
   for(int i=0;i<n;i++)
   {
      if(all[i].strength<ctx.min_score)
      { int s=ArraySize(dropped); if(ArrayResize(dropped,s+1)==s+1) dropped[s]=all[i]; }
      else if(ArraySize(out)<ctx.max_zones)
      { int s=ArraySize(out); if(ArrayResize(out,s+1)==s+1) out[s]=all[i]; }
      else
      { int s=ArraySize(tail); if(ArrayResize(tail,s+1)==s+1) tail[s]=all[i]; }
   }
}

// Resolve historical path geometry onto a current merged zone when available.
// This collapses A-B-C chains even when raw A and C do not overlap directly.
void UD_PathBand(const int index,double &lo,double &hi)
{
   lo=g_zre_sig[index].zone_lo; hi=g_zre_sig[index].zone_hi;
   int side=(g_zre_sig[index].is_buy?1:-1);
   for(int z=0;z<ArraySize(g_zre_zones);z++)
      if(UD_Near(lo,hi,side,g_zre_zones[z].lo,g_zre_zones[z].hi,
                 (g_zre_zones[z].side==ZRE_SUPPORT?1:-1),UD_Tolerance(g_atr)))
      { lo=g_zre_zones[z].lo; hi=g_zre_zones[z].hi; return; }
   for(int z=0;z<ArraySize(g_rxn_extra_zones);z++)
      if(UD_Near(lo,hi,side,g_rxn_extra_zones[z].lo,g_rxn_extra_zones[z].hi,
                 (g_rxn_extra_zones[z].side==ZRE_SUPPORT?1:-1),UD_Tolerance(g_atr)))
      { lo=g_rxn_extra_zones[z].lo; hi=g_rxn_extra_zones[z].hi; return; }
}

// One selected projection per merged same-side zone; strongest, then newest.
int UD_PathDuplicate(const int index,const int &selected[],const int count)
{
   if(!InpUnifiedDecision) return -1;
   double lo=0,hi=0; UD_PathBand(index,lo,hi);
   for(int k=0;k<count;k++)
   {
      double slo=0,shi=0; UD_PathBand(selected[k],slo,shi);
      if(UD_Near(lo,hi,(g_zre_sig[index].is_buy?1:-1),
                 slo,shi,(g_zre_sig[selected[k]].is_buy?1:-1),UD_Tolerance(g_atr))) return k;
   }
   return -1;
}

// Fixed-capacity cooldown. Live keys are never evicted: on saturation new keys
// are suppressed until a slot expires, preserving the no-repeat guarantee.
string g_ud_log_keys[UD_LOG_CAP];
datetime g_ud_log_times[UD_LOG_CAP];
bool UD_LogAllows(const string key)
{
   int cooldown=InpMessageCooldownBars;
   if(cooldown<=0) return true;
   if(cooldown>1000) cooldown=1000;
   int closed=g_rates_total-2;
   if(closed<0 || closed>=ArraySize(g_buf_t)) return false;
   datetime now=g_buf_t[closed];
   if(now<=0) return false;
   int free_slot=-1;
   for(int i=0;i<UD_LOG_CAP;i++)
   {
      if(g_ud_log_times[i]>now) { g_ud_log_times[i]=0; g_ud_log_keys[i]=""; }
      bool expired=(g_ud_log_times[i]==0);
      if(!expired)
      {
         int shift=iBarShift(_Symbol,(ENUM_TIMEFRAMES)_Period,g_ud_log_times[i],true);
         expired=(shift>cooldown); // shift 1 = latest closed, difference = shift-1
      }
      if(g_ud_log_keys[i]==key && !expired) return false;
      if(expired && free_slot<0) free_slot=i;
   }
   if(free_slot<0) return false;
   g_ud_log_keys[free_slot]=key; g_ud_log_times[free_slot]=now; return true;
}
#endif
