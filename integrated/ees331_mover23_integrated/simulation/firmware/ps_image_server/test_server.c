/* Host-side tests of the same portable protocol/ownership implementation.
 * CPU/cache callback is a command responder, not arithmetic hardware evidence.
 */
#include "server.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static uint8_t memory[EES331_DDR_BYTES],out[256];
static uint32_t epoch=0,current=0,acks=0,flushes=0,invalidates=0,timeout_on=0;
static int timeout_code=-1;
static uint32_t cpu_count[12];
static void put(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint32_t get(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static int rpc(void*c,uint32_t op,const uint32_t a[4],uint32_t r[4]){
 (void)c;cpu_count[op]++;memset(r,0,16);
 if(op==timeout_on)return timeout_code;
 if(op==8)epoch++;
 if(op==6){if(current>=4)return 2;r[0]=100+current;r[1]=0x2000+0x1000*current;r[2]=1024;r[3]=epoch;}
 if(op==7){CHECK(a[0]==100+current && a[1]==epoch);current++;acks++;}
 return 0;
}
static void flush(void*c,uint32_t a,uint32_t n){(void)c;CHECK(a+n<=EES331_DDR_BYTES);flushes++;}
static void invalidate(void*c,uint32_t a,uint32_t n){(void)c;CHECK(a+n<=EES331_DDR_BYTES);invalidates++;}
static uint8_t call(ees331_server*s,unsigned op,unsigned n,const uint32_t*a,uint16_t*size){uint8_t p[24]={0};for(unsigned i=0;i<n;i++)put(p+4*i,a[i]);return ees331_handle(s,3,op,p,(uint16_t)(4*n),out,size);}
int main(void){
 ees331_server s;uint16_t n=0;uint32_t a[6]={0};uint8_t blob[256];memset(blob,0xA5,sizeof blob);
 ees331_server_init(&s,memory);s.cpu=rpc;s.to_device=flush;s.from_device=invalidate;
 CHECK(ees331_crc32((const uint8_t*)"123456789",9)==0xCBF43926u);
 CHECK(call(&s,RPC_CAPS,0,a,&n)==S_OK && n==24 && get(out)==0x45455332u);
 CHECK(ees331_handle(&s,1,0,blob,64,out,&n)==S_STATE);
 a[0]=256;a[1]=7;CHECK(call(&s,RPC_MODEL_BEGIN,2,a,&n)==S_OK);
 CHECK(ees331_handle(&s,1,64,blob,64,out,&n)==S_STATE); // hole rejected
 CHECK(ees331_handle(&s,1,0,blob,256,out,&n)==S_OK);
 a[0]=0;CHECK(call(&s,RPC_MODEL_END,1,a,&n)==S_CRC);
 a[0]=ees331_crc32(blob,256);CHECK(call(&s,RPC_MODEL_END,1,a,&n)==S_OK);
 CHECK(ees331_handle(&s,1,0,blob,64,out,&n)==S_ACCESS); // sealed model
 CHECK(ees331_handle(&s,1,0xFFFFFFF0u,blob,64,out,&n)==S_RANGE);
 a[0]=0x20;a[1]=0;CHECK(call(&s,RPC_CFG_WRITE,2,a,&n)==S_ACCESS);
 a[0]=0x14;CHECK(call(&s,RPC_CFG_WRITE,2,a,&n)==S_OK);
 CHECK(call(&s,RPC_TEMPLATE_COMMIT,0,a,&n)==S_OK);
 for(unsigned f=0;f<4;f++){
  a[0]=f;a[1]=0x400+f*64;a[2]=0x2000+f*0x1000;a[3]=100+f;a[4]=64;a[5]=2048;
  CHECK(call(&s,RPC_DEFINE,6,a,&n)==S_OK);
 }
 a[0]=1;a[1]=0x400;a[2]=0x3000;a[3]=101;a[4]=64;a[5]=2048;
 CHECK(call(&s,RPC_DEFINE,6,a,&n)==S_RANGE); // input collision
 a[0]=4;CHECK(call(&s,RPC_START,1,a,&n)==S_OK);
 a[0]=256;a[1]=8;CHECK(call(&s,RPC_MODEL_BEGIN,2,a,&n)==S_STATE);
 for(unsigned f=0;f<4;f++){
  a[0]=f;a[1]=ees331_crc32(blob,64);a[2]=7;
  CHECK(call(&s,RPC_FRAME,3,a,&n)==S_STATE); // no whole image
  CHECK(ees331_handle(&s,1,0x400+f*64,blob,64,out,&n)==S_OK);
  a[1]^=1;CHECK(call(&s,RPC_FRAME,3,a,&n)==S_CRC);a[1]^=1;
  CHECK(call(&s,RPC_FRAME,3,a,&n)==S_OK);
  CHECK(ees331_handle(&s,1,0x400+f*64,blob,64,out,&n)==S_ACCESS);
  for(unsigned j=0;j<1024;j++)memory[0x2000+f*0x1000+j]=(uint8_t)(f+j);
 }
 for(unsigned f=0;f<4;f++){
  a[0]=100+f;a[1]=epoch;CHECK(call(&s,RPC_ACK,2,a,&n)==S_TOKEN); // not yet read
  for(unsigned off=0;off<1024;){
   a[0]=off;CHECK(call(&s,RPC_RESULT,1,a,&n)==S_OK);
   CHECK(get(out)==100+f && get(out+8)==1024 && get(out+12)==epoch);
   for(unsigned j=0;j<(unsigned)n-16u;j++)CHECK(out[16+j]==(uint8_t)(f+off+j));off+=(unsigned)n-16u;
  }
  a[0]=100+f;a[1]=epoch-1;CHECK(call(&s,RPC_ACK,2,a,&n)==S_TOKEN);
  a[1]=epoch;CHECK(call(&s,RPC_ACK,2,a,&n)==S_OK);CHECK(call(&s,RPC_ACK,2,a,&n)==S_OK);
 }
 CHECK(acks==4 && flushes==5 && invalidates>=20 && cpu_count[6]==20);
 CHECK(call(&s,RPC_BATCH_RESET,0,a,&n)==S_OK && s.running==0 && s.templates==0 && s.model_sealed);
 a[0]=256;a[1]=8;CHECK(call(&s,RPC_MODEL_BEGIN,2,a,&n)==S_OK && !s.model_sealed);
 // An ambiguous CPU command timeout latches a fail-closed transport fault.
 CHECK(ees331_handle(&s,1,0,blob,256,out,&n)==S_OK);
 a[0]=ees331_crc32(blob,256);CHECK(call(&s,RPC_MODEL_END,1,a,&n)==S_OK);
 CHECK(call(&s,RPC_TEMPLATE_COMMIT,0,a,&n)==S_OK);
 a[0]=0;a[1]=0x400;a[2]=0x2000;a[3]=100;a[4]=64;a[5]=2048;
 CHECK(call(&s,RPC_DEFINE,6,a,&n)==S_OK);
 a[0]=1;CHECK(call(&s,RPC_START,1,a,&n)==S_OK);
 CHECK(ees331_handle(&s,1,0x400,blob,64,out,&n)==S_OK);
 a[0]=0;a[1]=ees331_crc32(blob,64);a[2]=8;timeout_on=5;
 CHECK(call(&s,RPC_FRAME,3,a,&n)==S_TIMEOUT && s.transport_fault);
 timeout_on=0;unsigned count=cpu_count[5];
 CHECK(ees331_handle(&s,1,0x400,blob,64,out,&n)==S_TIMEOUT);
 CHECK(call(&s,RPC_FRAME,3,a,&n)==S_TIMEOUT && cpu_count[5]==count);
 CHECK(call(&s,RPC_BATCH_RESET,0,a,&n)==S_TIMEOUT);
 CHECK(call(&s,RPC_CAPS,0,a,&n)==S_OK);
 ees331_server_init(&s,memory);s.cpu=rpc;s.to_device=flush;s.from_device=invalidate;
 timeout_on=8;timeout_code=7;a[0]=256;a[1]=9;
 CHECK(call(&s,RPC_MODEL_BEGIN,2,a,&n)==S_TIMEOUT && s.transport_fault);
 CHECK(ees331_handle(&s,1,0,blob,64,out,&n)==S_TIMEOUT);
 puts("PASS EES331 PS server: bounds, CRC, ownership, four commits, fragmented results, epoch ACK, batch reuse, ambiguous timeout locks writes");return 0;
}
