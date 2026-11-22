#ifndef CNN_SIMPLE_H
#define CNN_SIMPLE_H
#include <stdint.h>
#include <stddef.h>
#define CNN_SIMPLE_ID 0x53434e31u
#define CNN_SIMPLE_PAGE(u) (((u)+1u)*0x100u)
typedef struct { uint32_t word[16]; } cnn_simple_descriptor;
typedef struct {
 void *context;
 uint32_t (*read32)(void *,uint32_t offset);
 void (*write32)(void *,uint32_t offset,uint32_t value);
 void (*io_fence)(void *);
} cnn_simple_io;
/* Raw UINT8 x INT8 valid convolution -> INT32. No bias or quantization.
 * Addresses are logical bank/DDR addresses, not host pointers. K3 units 0/1,
 * ordinary K1 units 2/3. All shape/extent multiplication happens in software.
 * Configure storage residency, perform cache maintenance and synchronize DMA
 * before submitting. The fence callback must provide the CPU's real I/O fence.
 */
static inline int cnn_simple_make(cnn_simple_descriptor *d,unsigned unit,
 uint32_t input,uint32_t weights,uint32_t output,uint32_t width,uint32_t height,
 uint32_t ci,uint32_t co,uint32_t stride,unsigned depthwise,uint32_t tag)
{
 if(!d||unit>3||!ci||ci>512||!co||co>512||width>65535||height>65535||
    (stride!=1&&stride!=2)||depthwise>1||(output&3))return -1;
 uint32_t k=unit<2?3:1;
 if(width<k||height<k||(depthwise&&(unit>=2||ci!=co)))return -1;
 uint64_t row=(uint64_t)width*ci,in=row*height;
 uint64_t per=(uint64_t)k*k*(depthwise?1:ci),wt=per*co;
 uint32_t ow=(width-k)/stride+1,oh=(height-k)/stride+1;
 uint64_t out=(uint64_t)ow*oh*co*4,ie=(uint64_t)input+in,we=(uint64_t)weights+wt,oe=(uint64_t)output+out;
 if(row>UINT32_MAX||in>UINT32_MAX||wt>UINT32_MAX||out>UINT32_MAX||
    ie>0x100000000ull||we>0x100000000ull||oe>0x100000000ull||
    ((uint64_t)output<ie&&(uint64_t)input<oe)||((uint64_t)output<we&&(uint64_t)weights<oe))return -1;
 unsigned reuse=depthwise||((ow>2||oh>2)&&wt<=9u*512u);
 uint32_t loaded=(uint32_t)(reuse?wt:per);
 uint32_t flags=0x80000000u|depthwise|(reuse?0x400u:0)|
  ((!(input&3)&&!(ci&3))?0x100u:0)|((!(weights&3)&&!(loaded&3))?0x200u:0);
 uint32_t w[16]={input,weights,output,width,height,ci,co,stride,depthwise,
  (uint32_t)row,(uint32_t)per,(uint32_t)in,(uint32_t)wt,flags,tag,0};
 for(unsigned n=0;n<16;n++)d->word[n]=w[n];
 return 0;
}
static inline int cnn_simple_submit(const cnn_simple_io *io,unsigned unit,const cnn_simple_descriptor *d)
{
 if(!io||!io->read32||!io->write32||!io->io_fence||!d||unit>3)return -1;
 uint32_t p=CNN_SIMPLE_PAGE(unit);
 if(io->read32(io->context,p+4)&1)return -2;
 io->write32(io->context,p,2);
 for(unsigned n=0;n<16;n++)io->write32(io->context,p+0x20+n*4,d->word[n]);
 io->io_fence(io->context);
 io->write32(io->context,p,1);
 return 0;
}
#endif
