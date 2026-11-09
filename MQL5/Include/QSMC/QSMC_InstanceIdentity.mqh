#ifndef QSMC_INSTANCE_IDENTITY_MQH
#define QSMC_INSTANCE_IDENTITY_MQH
// Diagnostic ABI v2 only. Trading buffers 7..12 are unchanged.
// FNV-1a fingerprint is an identity checksum, NOT a security primitive.
uint QSMC_IdentityHash(const string text,const uint seed=0x811C9DC5)
{
   uint h=seed;
   for(int i=0;i<StringLen(text);i++) h=(h^(uint)StringGetCharacter(text,i))*(uint)16777619;
   return h;
}
void QSMC_AddInputHash(uint &h,const string key,const string value)
{
   h=QSMC_IdentityHash(key+"#"+IntegerToString(StringLen(value))+":"+value+";",h);
}
string QSMC_InstanceBase()
{
   string scope=AccountInfoString(ACCOUNT_SERVER)+"|"+IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+"|"+_Symbol;
   return "QSMC_I2_"+IntegerToString((long)QSMC_IdentityHash(scope))+"_"+IntegerToString((long)_Period)+"_";
}
string QSMC_DefaultDiagPrefix()
{
   string base=QSMC_InstanceBase();
   if(!GlobalVariableCheck(base+"DEFAULT_HASH") || !GlobalVariableCheck(base+"DEFAULT_SEEN")) return "";
   if(TimeCurrent()-(datetime)GlobalVariableGet(base+"DEFAULT_SEEN")>300) return "";
   return base+"D"+IntegerToString((long)GlobalVariableGet(base+"DEFAULT_HASH"))+"_";
}

// Host-only adaptation (the EA includes only the common diagnostic reader).
#ifdef QSMC_HOST_IDENTITY
void QA_InputHashes(uint &actual,uint &defaults); // generated complete manifest

// 2026-11-09 (section 3): the instance-mismatch test is ROLE-AWARE.
//
// QSMC_InstanceBase() is scoped by (server, login, symbol, timeframe) - NOT by
// role - and every instance published the same key "H"+input_hash. So the
// VISUAL instance on the chart and the EA_READER instance created by the EA's
// iCustom call compared their input hashes with each other. They are not
// supposed to match when the chart has a .set loaded: the EA passes no input
// list at all (compiled defaults by design) while the panel may be tuned. The
// reader then saw "INSTANCE MISMATCH", QA_CoreDisplayRefresh() returned before
// publishing, the panel read "INSTANCE MISMATCH - WAIT" and the EA's heartbeat
// read "CORE signals ...: 0". One operator-facing symptom, two unrelated causes.
//
// The role is NOT part of the input hash (the generated manifest covers the 576
// inputs only), so the fix is not "hash the role": it is to compare like with
// like. Each role publishes and scans its own namespace H<role>_<hash>; the
// legacy H<hash> key is still written so an older reader sees the shape it
// always did.
int g_qa_instance_role=-1;
void QA_SetInstanceRole(const int role) { g_qa_instance_role=role; }
string QA_RoleTag() { return (g_qa_instance_role>=0 ? IntegerToString(g_qa_instance_role)+"_" : ""); }
string QA_InstanceDiagPrefix()
{
   uint actual=0,defaults=0; QA_InputHashes(actual,defaults);
   return QSMC_InstanceBase()+"D"+IntegerToString((long)actual)+"_";
}
void QA_InstancePublish()
{
   uint actual=0,defaults=0; QA_InputHashes(actual,defaults);
   static datetime last=0;
   datetime now=TimeCurrent(); if(now<=0 || now==last) return; last=now;
   string base=QSMC_InstanceBase();
   GlobalVariableSet(base+"H"+QA_RoleTag()+IntegerToString((long)actual),(double)now);
   // Legacy name (no role tag): kept so a reader built before 2026-11-09 still sees it.
   GlobalVariableSet(base+"H"+IntegerToString((long)actual),(double)now);
   if(actual==defaults)
   {
      GlobalVariableSet(base+"DEFAULT_HASH",(double)defaults);
      GlobalVariableSet(base+"DEFAULT_SEEN",(double)now);
   }
   static bool logged=false;
   if(!logged)
   {
      logged=true;
      Print("[QSMC_INSTANCE] symbol=",_Symbol," tf=",EnumToString((ENUM_TIMEFRAMES)_Period),
            " chart=",ChartID()," input_hash=",actual," EA_DEFAULT_hash=",defaults,
            " config=",(actual==defaults?"DEFAULT-equivalent":"CUSTOM"),
            " | EA authority=private iCustom DEFAULT inputs; visible Inputs are NOT inherited");
   }
}
bool QA_InstanceMismatch()
{
   uint actual=0,defaults=0; QA_InputHashes(actual,defaults);
   // Role-scoped: a VISUAL panel with a chart .set is not a mismatch for the
   // EA_READER instance that runs on compiled defaults (see the note above).
   string prefix=QSMC_InstanceBase()+"H"+QA_RoleTag(),own=prefix+IntegerToString((long)actual);
   datetime now=TimeCurrent();
   for(int i=GlobalVariablesTotal()-1;i>=0;i--)
   {
      string key=GlobalVariableName(i);
      if(key==own || StringFind(key,prefix)!=0) continue;
      datetime seen=(datetime)GlobalVariableGet(key);
      if(seen<=now && now-seen<=300) return true;
   }
   return false;
}
string QA_InstanceDescription()
{
   uint actual=0,defaults=0; QA_InputHashes(actual,defaults);
   return (QA_InstanceMismatch()?"INSTANCE MISMATCH | ":"")+string("role ")+
          (g_qa_instance_role>=0 ? IntegerToString(g_qa_instance_role) : string("?"))+
          string(" input hash ")+IntegerToString((long)actual)+
          " | EA DEFAULT hash "+IntegerToString((long)defaults)+
          " | compared only against the SAME role (a tuned VISUAL panel is expected, not a fault)";
}
#endif
#endif
