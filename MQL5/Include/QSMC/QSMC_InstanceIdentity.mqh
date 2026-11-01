#ifndef QSMC_INSTANCE_IDENTITY_MQH
#define QSMC_INSTANCE_IDENTITY_MQH
// Diagnostic ABI v2 only. Trading buffers 7..12 are unchanged.
// FNV-1a fingerprint is an identity checksum, NOT a security primitive.
uint QSMC_IdentityHash(const string text,const uint seed=2166136261)
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
   string prefix=QSMC_InstanceBase()+"H",own=prefix+IntegerToString((long)actual);
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
   return (QA_InstanceMismatch()?"INSTANCE MISMATCH | ":"")+string("input hash ")+IntegerToString((long)actual)+
          " | EA DEFAULT hash "+IntegerToString((long)defaults)+" (private iCustom, no inheritance)";
}
#endif
#endif
