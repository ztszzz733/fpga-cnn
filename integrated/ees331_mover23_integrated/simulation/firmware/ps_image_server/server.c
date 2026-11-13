#include "server.h"
#include <string.h>

static uint32_t get32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t*p,uint32_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);p[2]=(uint8_t)(x>>16);p[3]=(uint8_t)(x>>24);}
uint32_t ees331_crc32(const uint8_t*p,size_t n){uint32_t c=~0u;while(n--){c^=*p++;for(unsigned k=0;k<8;k++)c=(c>>1)^((0u-(c&1u))&0xEDB88320u);}return ~c;}
static uint32_t memory_crc(ees331_server*s,uint32_t a,uint32_t n){
 uint32_t c=~0u;s->from_device(s->opaque,a,n);
 for(uint32_t i=0;i<n;i++){c^=s->ddr[a+i];for(unsigned k=0;k<8;k++)c=(c>>1)^((0u-(c&1u))&0xEDB88320u);}return ~c;
}
void ees331_server_init(ees331_server*s,volatile uint8_t*d){memset(s,0,sizeof *s);s->ddr=d;}
static int within(uint32_t a,uint32_t n){return n && a<EES331_DDR_BYTES && n<=EES331_DDR_BYTES-a;}
static int overlaps(uint32_t a,uint32_t n,uint32_t b,uint32_t m){return a<b+m && b<a+n;}
static int quiescent(ees331_server*s){if(!s->running)return 1;for(unsigned i=0;i<s->frames;i++)if(!s->frame[i].acked)return 0;return 1;}
static int cpu(ees331_server*s,uint32_t op,uint32_t a,uint32_t b,uint32_t c,uint32_t d,uint32_t*r){
 uint32_t args[4]={a,b,c,d},discard[4];int rc=s->cpu(s->opaque,op,args,r?r:discard);
 // A timeout has an UNKNOWN side-effect outcome. A late FRAME may still be
 // accepted by the CPU; never leave its input writable after losing the ACK.
 // Firmware status7 is a cache-maintenance timeout: its AXI transaction may
 // likewise still be draining even though the mailbox ACK itself arrived.
 if(rc<0 || rc==7)s->transport_fault=1;return rc;
}
static uint8_t cpu_error(ees331_server*s){return s->transport_fault?S_TIMEOUT:S_CPU;}
static uint8_t write_memory(ees331_server*s,uint32_t a,const uint8_t*p,uint32_t n){
 if(!within(a,n))return S_RANGE;
 if(s->model_upload && a==s->model_received && a+n<=s->model_end){
  for(uint32_t i=0;i<n;i++)s->ddr[a+i]=p[i];s->to_device(s->opaque,a,n);s->model_received+=n;return S_OK;
 }
 if(!s->model_sealed)return S_STATE;
 for(unsigned f=0;f<4;f++){
  ees331_frame*t=&s->frame[f];
  if(t->defined && !t->committed && a==t->input+t->received && n<=t->length-t->received){
   for(uint32_t i=0;i<n;i++)s->ddr[a+i]=p[i];s->to_device(s->opaque,a,n);t->received+=n;return S_OK;
  }
 }
 return S_ACCESS;
}
static uint8_t read_memory(ees331_server*s,uint32_t a,uint32_t n,uint8_t*out){
 if(!within(a,n))return S_RANGE;
 // Raw reads are for upload verification. Results require the fenced RPC.
 int allowed=(a+n<=s->model_received);
 for(unsigned f=0;f<4;f++){ees331_frame*t=&s->frame[f];if(t->defined && a>=t->input && a+n<=t->input+t->received)allowed=1;}
 if(!allowed)return S_ACCESS;
 s->from_device(s->opaque,a,n);for(uint32_t i=0;i<n;i++)out[i]=s->ddr[a+i];return S_OK;
}
uint8_t ees331_handle(ees331_server*s,uint8_t op,uint32_t address,const uint8_t*in,uint16_t n,uint8_t*out,uint16_t*out_n){
 uint32_t a[6]={0},r[4]={0};*out_n=0;
 if(n>EES331_MAX_PACKET || !s->cpu || !s->to_device || !s->from_device)return S_COMMAND;
 if(s->transport_fault && !(op==3 && address==RPC_CAPS && n==0))return S_TIMEOUT;
 if(op==1)return n?write_memory(s,address,in,n):S_COMMAND;
 if(op==2){uint8_t e=n?read_memory(s,address,n,out):S_COMMAND;if(!e)*out_n=n;return e;}
 if(op!=3 || n%4 || n>24)return S_COMMAND;
 for(unsigned i=0;i<(unsigned)n/4u;i++)a[i]=get32(in+4*i);
 switch(address){
 case RPC_CAPS:
  if(n)return S_COMMAND;
  put32(out,0x45455332u);put32(out+4,1);put32(out+8,EES331_DDR_BYTES);
  put32(out+12,4);put32(out+16,128);put32(out+20,s->model_version);*out_n=24;return S_OK;
 case RPC_MODEL_BEGIN:
  if(n!=8 || !a[0] || a[0]>=EES331_DDR_BYTES || (a[0]&63))return S_RANGE;
  if(!quiescent(s))return S_STATE;
  if(cpu(s,8,0,0,0,0,0) || cpu(s,9,0x14,0,0,0,0))return cpu_error(s);
  memset(s->frame,0,sizeof s->frame);s->running=0;s->templates=0;s->frames=0;
  s->model_upload=1;s->model_sealed=0;s->model_received=0;s->model_end=a[0];s->model_version=a[1];return S_OK;
 case RPC_MODEL_END:
  if(n!=4)return S_COMMAND;
  if(!s->model_upload || s->model_received!=s->model_end)return S_STATE;
  if(memory_crc(s,0,s->model_end)!=a[0])return S_CRC;
  if(cpu(s,9,0x10,s->model_end,0,0,0) || cpu(s,9,0x14,1,0,0,0))return cpu_error(s);
  s->model_upload=0;s->model_sealed=1;return S_OK;
 case RPC_CFG_WRITE:
  if(n!=8 || !s->model_sealed || s->running)return S_STATE;
  // Address descriptors and frame metadata use the checked DEFINE operation.
  if(!(a[0]==0x0c || a[0]==0x10 || a[0]==0x14 || a[0]==0x18 || a[0]==0x1c))return S_ACCESS;
  return cpu(s,2,a[0],a[1],0,0,0)?cpu_error(s):S_OK;
 case RPC_TEMPLATE_COMMIT:
  if(n || !s->model_sealed || s->running || s->templates>=256)return S_STATE;
  if(cpu(s,3,4,0,0,0,0))return cpu_error(s);s->templates++;return S_OK;
 case RPC_DEFINE:{
  if(n!=24 || !s->model_sealed || s->running || a[0]>=4)return S_STATE;
  unsigned slot=a[0];uint32_t input=a[1],work=a[2],id=a[3],len=a[4],worklen=a[5];
  if(!within(input,len) || !within(work,worklen) || ((input|work|len|worklen)&63) ||
     input<s->model_end || work<s->model_end || overlaps(input,len,work,worklen))return S_RANGE;
  for(unsigned f=0;f<4;f++)if(f!=slot && s->frame[f].defined){ees331_frame*t=&s->frame[f];
   if(id==t->id || overlaps(input,len,t->input,t->length) || overlaps(input,len,t->workspace,t->workspace_bytes) ||
      overlaps(work,worklen,t->input,t->length) || overlaps(work,worklen,t->workspace,t->workspace_bytes))return S_RANGE;
  }
  if(cpu(s,2,0x20,slot,0,0,0)||cpu(s,2,0x24,input,0,0,0)||cpu(s,2,0x28,work,0,0,0)||
     cpu(s,2,0x2c,id,0,0,0)||cpu(s,3,8,0,0,0,0))return cpu_error(s);
  ees331_frame*t=&s->frame[slot];memset(t,0,sizeof *t);t->defined=1;
  t->input=input;t->workspace=work;t->workspace_bytes=worklen;t->id=id;t->length=len;return S_OK;
 }
 case RPC_START:
  if(n!=4 || !s->model_sealed || s->running || !s->templates || a[0]<1 || a[0]>4)return S_STATE;
  for(unsigned f=0;f<a[0];f++)if(!s->frame[f].defined)return S_STATE;
  if(cpu(s,2,0x0c,a[0],0,0,0)||cpu(s,4,0,0,0,0,0))return cpu_error(s);
  s->frames=a[0];s->running=1;return S_OK;
 case RPC_FRAME:{
  if(n!=12 || !s->running || a[0]>=s->frames || a[2]!=s->model_version)return S_STATE;
  ees331_frame*t=&s->frame[a[0]];
  if(t->committed)return S_STATE;
  if(t->received!=t->length)return S_STATE;
  if(memory_crc(s,t->input,t->length)!=a[1])return S_CRC;
  if(cpu(s,5,a[0],t->id,0,0,0))return cpu_error(s);
  t->committed=1;return S_OK;
 }
 case RPC_RESULT:{
  if((n!=0 && n!=4) || !s->running)return S_STATE;
  int rc=cpu(s,6,0,0,0,0,r);if(rc==2)return S_STATE;if(rc)return cpu_error(s);
  if(!within(r[1],r[2]) || a[0]>=r[2])return S_RANGE;
  ees331_frame*t=0;for(unsigned f=0;f<s->frames;f++)if(s->frame[f].id==r[0])t=&s->frame[f];
  if(!t || !t->committed || t->acked || r[1]<t->workspace || r[1]>=t->workspace+t->workspace_bytes ||
     r[2]>t->workspace+t->workspace_bytes-r[1] || a[0]!=t->result_read)return S_STATE;
  // CPU has completed the PL write-back fence including AXI B response.
  uint32_t count=r[2]-a[0];if(count>EES331_MAX_PACKET-16)count=EES331_MAX_PACKET-16;
  s->from_device(s->opaque,r[1]+a[0],count);for(unsigned i=0;i<4;i++)put32(out+4*i,r[i]);
  for(uint32_t i=0;i<count;i++)out[16+i]=s->ddr[r[1]+a[0]+i];
  t->result_read+=count;t->result_seen=t->result_read==r[2];t->epoch=r[3];
  *out_n=(uint16_t)(16+count);return S_OK;
 }
 case RPC_ACK:{
  if(n!=8 || !s->running)return S_STATE;
  ees331_frame*t=0;for(unsigned f=0;f<s->frames;f++)if(s->frame[f].id==a[0])t=&s->frame[f];
  if(!t || !t->result_seen || t->epoch!=a[1])return S_TOKEN;
  if(t->acked)return S_OK;
  if(cpu(s,7,a[0],a[1],0,0,0))return cpu_error(s);t->acked=1;return S_OK;
 }
 case RPC_STATUS:
  if(n)return S_COMMAND;
  if(cpu(s,10,0,0,0,0,r))return cpu_error(s);for(unsigned i=0;i<4;i++)put32(out+4*i,r[i]);
  put32(out+16,s->model_version);put32(out+20,s->frames);*out_n=24;return S_OK;
 case RPC_BATCH_RESET:
  if(n || !quiescent(s))return S_STATE;
  if(cpu(s,8,0,0,0,0,0))return cpu_error(s);
  memset(s->frame,0,sizeof s->frame);s->running=0;s->templates=0;s->frames=0;return S_OK;
 default:return S_COMMAND;
 }
}
