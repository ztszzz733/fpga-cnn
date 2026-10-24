/* Xilinx standalone Cortex-A9 application. Build against the exact EES331 XSA.
 * DDR/PS clocks are initialized by the matching FSBL/ps7_init, not by this file.
 * Application DDR/linker range MUST exclude [0x10000000,0x12000000).
 */
#include "server.h"
#include "xparameters.h"
#include "xuartps.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include <string.h>
#if !defined(SDT) && !defined(EES331_UART_DEVICE_ID)
#define EES331_UART_DEVICE_ID XPAR_XUARTPS_0_DEVICE_ID
#endif
#ifndef EES331_UART_BAUD
#define EES331_UART_BAUD 115200u
#endif
#define UART1_BASE 0xE0001000u
#define MB(a) (EES331_MAILBOX_BASE+(a))
static XUartPs uart;
static ees331_server server;
static uint32_t seq;
static uint32_t u32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void w32(uint8_t*p,uint32_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);p[2]=(uint8_t)(x>>16);p[3]=(uint8_t)(x>>24);}
static void barrier(void){__asm__ volatile("dsb sy":::"memory");}
static int elapsed(XTime start,unsigned seconds){XTime now;XTime_GetTime(&now);return now-start>(XTime)COUNTS_PER_SECOND*seconds;}
static void to_device(void*ctx,uint32_t a,uint32_t n){(void)ctx;Xil_DCacheFlushRange(EES331_DDR_BASE+a,n);barrier();}
static void from_device(void*ctx,uint32_t a,uint32_t n){(void)ctx;barrier();Xil_DCacheInvalidateRange(EES331_DDR_BASE+a,n);barrier();}
static int cpu_rpc(void*ctx,uint32_t op,const uint32_t a[4],uint32_t r[4]){
 (void)ctx;XTime start;XTime_GetTime(&start);
 while(Xil_In32(MB(8))!=Xil_In32(MB(12)))if(elapsed(start,10))return -1;
 Xil_Out32(MB(16),op);for(unsigned i=0;i<4;i++)Xil_Out32(MB(20+4*i),a[i]);barrier();
 seq=Xil_In32(MB(8))+1;Xil_Out32(MB(8),seq);barrier();XTime_GetTime(&start);
 while(Xil_In32(MB(12))!=seq)if(elapsed(start,10))return -1;
 barrier();for(unsigned i=0;i<4;i++)r[i]=Xil_In32(MB(84+4*i));
 return (int)Xil_In32(MB(80));
}
static int receive(uint8_t*out,unsigned n,unsigned timeout){
 XTime start;XTime_GetTime(&start);
 for(unsigned i=0;i<n;){
  if(XUartPs_IsReceiveData(uart.Config.BaseAddress)){out[i++]=(uint8_t)XUartPs_ReadReg(uart.Config.BaseAddress,XUARTPS_FIFO_OFFSET);XTime_GetTime(&start);}
  else if(elapsed(start,timeout))return -1;
 }return 0;
}
static void transmit(const uint8_t*p,unsigned n){for(unsigned i=0;i<n;i++)XUartPs_SendByte(uart.Config.BaseAddress,p[i]);}
static int ddr_selftest(void){
 // Scratch is in the reserved SECOND 16MiB window, outside CNN/cache reach.
 // Never overwrite model/input/intermediates even when this app is restarted.
 const uint32_t scratch=EES331_DDR_BYTES;
 volatile uint32_t*p=(volatile uint32_t*)(EES331_DDR_BASE+scratch);
 for(unsigned i=0;i<1024;i++)p[i]=0x5A69C300u^i;
 to_device(0,scratch,4096);from_device(0,scratch,4096);
 for(unsigned i=0;i<1024;i++)if(p[i]!=(0x5A69C300u^i))return -1;
 return 0;
}
int main(void){
#ifdef SDT
 XUartPs_Config*cfg=XUartPs_LookupConfig(UART1_BASE);
#else
 XUartPs_Config*cfg=XUartPs_LookupConfig(EES331_UART_DEVICE_ID);
#endif
 // Fail closed if the BSP selected UART0 or an unrelated serial controller.
 if(!cfg || cfg->BaseAddress!=UART1_BASE || XUartPs_CfgInitialize(&uart,cfg,cfg->BaseAddress)!=XST_SUCCESS)return 1;
 if(XUartPs_SetBaudRate(&uart,EES331_UART_BAUD)!=XST_SUCCESS)return 2;
 XUartPs_SetOperMode(&uart,XUARTPS_OPER_MODE_NORMAL);
 XTime start;XTime_GetTime(&start);
 while(Xil_In32(MB(100))!=0x43505532u)if(elapsed(start,10))return 4;
 if(Xil_In32(MB(0))!=0x45455332u)return 5;
 uint32_t init[4]={0x44524459u,0,0,0},result[4];
 // Warm-starting PS software must not create a second owner of a running or
 // faulted CNN batch. STATUS is allowed before publishing DDR_READY.
 uint32_t zero[4]={0,0,0,0};
 if(cpu_rpc(0,10,zero,result) || (result[0]&10u) || (result[2]&28u))return 7;
 XTime_GetTime(&start);
 while(!(result[2]&1u) || (result[2]&2u)){
  if(elapsed(start,10) || cpu_rpc(0,10,zero,result) ||
     (result[0]&10u) || (result[2]&28u))return 7;
 }
 if(ddr_selftest())return 3;
 if(cpu_rpc(0,1,init,result))return 6;
 ees331_server_init(&server,(volatile uint8_t*)EES331_DDR_BASE);
 server.cpu=cpu_rpc;server.to_device=to_device;server.from_device=from_device;
 uint8_t request[272],last_request[272],response[272],last_response[272];
 unsigned last_request_n=0,last_response_n=0;
 for(;;){
  // Resynchronize after a truncated request without interpreting stray bytes.
  unsigned magic=0;
  while(magic<4){uint8_t b;if(receive(&b,1,30))continue;if(b==(uint8_t)"IMIO"[magic])request[magic++]=b;else magic=b=='I'?(request[0]='I',1):0;}
  if(receive(request+4,8,2))continue;
  uint8_t op=request[4],tag=request[5];uint16_t n=(uint16_t)(request[6]|request[7]<<8);
  uint32_t address=u32(request+8);unsigned payload=(op==1 || op==3)?n:0;
  if(n>256 || (op!=1 && op!=2 && op!=3))continue;
  if(receive(request+12,payload+4,2))continue;
  unsigned packet_n=16+payload;
  if(packet_n==last_request_n && !memcmp(request,last_request,packet_n)){
   transmit(last_response,last_response_n);continue;
  }
  uint16_t out_n=0;uint8_t status;
  if(ees331_crc32(request,packet_n-4)!=u32(request+packet_n-4))status=S_CRC;
  else status=ees331_handle(&server,op,address,request+12,n,response+12,&out_n);
  memcpy(response,"IMOR",4);response[4]=status;response[5]=tag;
  response[6]=(uint8_t)out_n;response[7]=(uint8_t)(out_n>>8);w32(response+8,address);
  w32(response+12+out_n,ees331_crc32(response,12+out_n));
  unsigned response_n=16+out_n;
  // Cache exactly one complete packet/response. Immediate retry after a lost
  // reply is idempotent; a new packet with the same 8-bit tag is not a duplicate.
  memcpy(last_request,request,packet_n);last_request_n=packet_n;
  memcpy(last_response,response,response_n);last_response_n=response_n;
  transmit(response,response_n);
 }
}
