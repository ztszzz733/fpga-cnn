#include "cnn_frames.h"

/* Runtime data/configs are in SRAM, instructions alone are in IMEM.
   gen_neureka_frames.py defines the simulation dataset and independent oracle. */
static void stop(uint32_t code) {
    *cnn_reg(0x80)=code;
    for(;;) __asm__ volatile ("nop");
}
void *memcpy(void *dst,const void *src,unsigned n) {
    unsigned char *d=dst;const unsigned char *s=src;
    for(unsigned i=0;i<n;i++) d[i]=s[i];
    return dst;
}
void *memset(void *dst,int c,unsigned n) {
    unsigned char *d=dst;for(unsigned i=0;i<n;i++) d[i]=(unsigned char)c;return dst;
}
void main(void) {
    cnn_frames queue;cnn_frame layout[2];
    cnn_region protected_regions[5];
    protected_regions[0]=(cnn_region){0x4000,1440};
    protected_regions[1]=(cnn_region){0x4800,20};
    protected_regions[2]=(cnn_region){0x5000,0x100};
    protected_regions[3]=(cnn_region){0x20000,0x4000};
    protected_regions[4]=(cnn_region){0x38000,0x8000};
    volatile uint32_t *spec=cnn_reg(0x5000);
    uint32_t submitted=0,consumed=0,work=0,budget=2000000;
    uint32_t measured[2];measured[0]=0xffffffffu;measured[1]=0xffffffffu;
    for(unsigned s=0;s<2;s++) {
        layout[s].image=(cnn_image_job){0,0x2000+s*0x1000,405,0};
        layout[s].cnn=(cnn_pipeline_job){0x100+s*0x100,4,0x10000,0x11000,0x400,0};
        layout[s].configs=(cnn_region){0x1000+s*0x200,384};
        layout[s].output=(cnn_region){0x12000+s*0x1000,455};
        layout[s].state=CNN_FRAME_FREE;layout[s].sequence=0;
    }
    uint32_t vector_bytes=spec[0];
    if(cnn_pipeline_load_program((const uint32_t *)(uintptr_t)0x20000,vector_bytes/4)) stop(0xdead0001);
    /* Prove bad layouts are rejected before any transfer can start. */
    layout[1].image.destination=layout[0].image.destination;
    if(cnn_frames_init(&queue,layout,protected_regions,5)!=-14) stop(0xdead0002);
    layout[1].image.destination=0x3000;
    if(cnn_frames_init(&queue,layout,protected_regions,5)) stop(0xdead0003);
    for(unsigned s=0;s<2;s++) {
        if(cnn_frame_submit(&queue,s,spec[4+submitted*4],spec[5+submitted*4])) stop(0xdead0004);
        submitted++;
        if(cnn_frame_submit(&queue,s,0,0)!=-16 || cnn_frame_release(&queue,s)!=-18) stop(0xdead0005);
    }
    while(consumed<4 && budget--) {
        int rc=cnn_frames_poll(&queue);
        if(rc) { *cnn_reg(0x90)=(uint32_t)rc;stop(0xdead0006); }
        if(queue.running>=0) {
            unsigned s=(unsigned)queue.running;uint32_t sequence=queue.frame[s].sequence;
            if(measured[s]!=sequence) {
                /* Read-only image statistics can run alongside CNN input reads. */
                volatile unsigned char *input=(volatile unsigned char *)(uintptr_t)layout[s].image.destination;
                uint32_t sum=0;
                for(unsigned i=0;i<405;i++) { sum+=input[i];work++; }
                if(sum!=spec[7+sequence*4]) stop(0xdead000c);
                measured[s]=sequence;
            }
        }
        for(unsigned s=0;s<2;s++) if(queue.frame[s].state==CNN_FRAME_RESULT) {
            uint32_t sequence=queue.frame[s].sequence;
            if(sequence!=consumed) stop(0xdead0007);
            /* Useful CPU work on the previous result while the next CNN runs.
               The unconsumed output remains owned until this checksum ends. */
            volatile unsigned char *output=(volatile unsigned char *)(uintptr_t)layout[s].output.address;
            uint32_t sum=0;
            for(unsigned i=0;i<455;i++) {
                sum+=output[i];
                if(queue.running>=0) work++;
            }
            if(sum!=spec[6+sequence*4]) stop(0xdead0008);
            if(cnn_frame_release(&queue,s)) stop(0xdead0009);
            consumed++;
            if(submitted<4) {
                if(cnn_frame_submit(&queue,s,spec[4+submitted*4],spec[5+submitted*4])) stop(0xdead000a);
                submitted++;
            }
        }
        *cnn_reg(0x84)=submitted;*cnn_reg(0x88)=consumed;*cnn_reg(0x8c)=work;
    }
    if(consumed!=4) stop(0xdead000b); /* No buffer release on timeout. */
    stop(0x600dcafe);
}
