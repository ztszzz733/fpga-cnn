
typedef unsigned int u32;
#define REG(a) (*(volatile u32 *)(a))
#define PORT 0x40000000u
#define VEC 0x40040000u
__attribute__((noreturn)) void fail(u32 n) { REG(0x80)=0xbad00000u|n; for(;;){} }
static u32 transaction(u32 address,u32 value,u32 command) {
 REG(PORT)=address; REG(PORT+4)=value; REG(PORT+8)=command;
 for(u32 n=0;n<100000;n++) {
  u32 s=REG(PORT+12);
  if(s&4)fail(1);
  if((s&3)==2)return REG(PORT+16);
 }
 fail(2);
}
static void wr(u32 a,u32 d){transaction(a,d,1);}
static u32 rd(u32 a){return transaction(a,0,2);}
static void poll(u32 a,u32 value,u32 mask) {
 for(u32 n=0;n<20000;n++)if((rd(a)&mask)==value)return;
 fail(3);
}
static void vec_setup(u32 src,u32 dst,u32 count,u32 mode) {
 wr(VEC+4,src);wr(VEC+8,dst);wr(VEC+12,count);wr(VEC+16,mode);
}
static void vec_wait(void){poll(VEC,2,3);if(rd(VEC)&12)fail(4);if(rd(VEC+20))fail(5);}

void main(void) {
 REG(0x84)=1;
 for(u32 i=0;i<304;i+=4)wr(VEC+0x1000+i,REG(0x20000+i));
 vec_setup(0x30000,0x31000,256,1);
 REG(0x84)=2;
 wr(0x4000b018u,0x7u);
wr(0x4000b030u,0x701c07u);
wr(0x4000b06cu,0x200u);
wr(0x4000a028u,0x200u);
wr(0x4000b068u,0x40u);
wr(0x4000a024u,0x40u);
wr(0x4000b01cu,0x7u);
wr(0x4000a034u,0x0u);
wr(0x4000b034u,0x101u);
wr(0x4000a038u,0x1u);
wr(0x4000b020u,0x3fu);
wr(0x4000b078u,0x40u);
wr(0x4000b084u,0x0u);
wr(0x4000a030u,0x0u);
wr(0x4000b040u,0x1100u);
wr(0x4000b010u,0x7u);
wr(0x4000a010u,0x7u);
wr(0x4000b02cu,0x701c07u);
wr(0x4000a040u,0x701c07u);
wr(0x4000b00cu,0x7u);
wr(0x4000a00cu,0x7u);
wr(0x4000b024u,0x11u);
wr(0x4000a018u,0x1u);
wr(0x4000b07cu,0x200u);
wr(0x4000b080u,0x1u);
wr(0x4000a02cu,0x1u);
wr(0x4000b014u,0x3fu);
wr(0x4000a014u,0x3fu);
wr(0x4000a01cu,0x1000u);
wr(0x4000a020u,0x0u);
wr(0x4000b060u,0x1000u);
wr(0x4000b064u,0x0u);
wr(0x4000b070u,0x2000u);
wr(0x4000b074u,0x0u);
wr(VEC,1);
wr(0x4000a008u,0x1u);
wr(0x4000b008u,0x1u);
REG(0x84)=3; poll(PORT+0x100c,0x10u,0x10u);
 REG(0x84)=4;vec_wait();
 REG(0x84)=5;
 vec_setup(0x2000,0x18000,4096,0);wr(VEC,1);vec_wait();
 // Repeat without resetting SoC; verify per-job done clearing and core restart.
 REG(0x84)=6;
 vec_setup(0x2000,0x1a000,3,0);wr(VEC,1);vec_wait();
 REG(0x84)=7;
 REG(0x80)=0x600dcafe;
 for(;;){}
}
