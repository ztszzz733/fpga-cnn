#ifndef CNN_FRAMES_H
#define CNN_FRAMES_H
#include "neureka_pipeline.h"

/* These addresses match face_soc_neureka_pipeline_top. No new MMIO ports. */
#ifndef CNN_LOAD_CONTROL
#define CNN_LOAD_CONTROL 0x40u
#endif
#ifndef CNN_LOAD_DESCRIPTOR
#define CNN_LOAD_DESCRIPTOR 0x60u
#endif
#ifndef CNN_SRAM_BASE
#define CNN_SRAM_BASE 0u
#endif
#ifndef CNN_SRAM_SIZE
#define CNN_SRAM_SIZE 0x40000u
#endif
typedef struct { uint32_t address, bytes; } cnn_region;
typedef struct { uint32_t source, destination, bytes, crc32; } cnn_image_job;
typedef enum { CNN_FRAME_FREE, CNN_FRAME_QUEUED, CNN_FRAME_LOADING,
    CNN_FRAME_READY, CNN_FRAME_RUNNING, CNN_FRAME_RESULT } cnn_frame_state;
typedef struct {
    cnn_image_job image;
    cnn_pipeline_job cnn;
    cnn_region configs, output;
    cnn_frame_state state;
    uint32_t sequence;
} cnn_frame;
typedef struct {
    cnn_frame frame[2];
    int loading, running, acknowledging, load_failed, error;
    uint32_t submitted, started;
} cnn_frames;

static inline void cnn_memory_fence(void) { __asm__ volatile ("fence" ::: "memory"); }
static inline int cnn_region_valid(cnn_region r) {
    return r.bytes && (uint64_t)r.address-CNN_SRAM_BASE<CNN_SRAM_SIZE &&
        (uint64_t)r.address+r.bytes<=(uint64_t)CNN_SRAM_BASE+CNN_SRAM_SIZE;
}
static inline int cnn_regions_overlap(cnn_region a, cnn_region b) {
    return (uint64_t)a.address<(uint64_t)b.address+b.bytes &&
        (uint64_t)b.address<(uint64_t)a.address+a.bytes;
}
static inline int cnn_region_contains(cnn_region r, uint32_t a, uint32_t n) {
    return n && a>=r.address && (uint64_t)a+n<=(uint64_t)r.address+r.bytes;
}
/* Call after reset, with hardware idle and the vector program already loaded.
   Declare weights, scale tables, vector source, stack and application data as
   protected regions. All listed regions must be non-overlapping. Tile native
   strides and their full input/weight footprints remain the caller's contract. */
static inline int cnn_frames_init(cnn_frames *q, const cnn_frame layout[2],
                                  const cnn_region *protected_regions, uint32_t count) {
    cnn_region regions[20]; uint32_t n=0, status; int rc;
    if(!q || !layout || count>8 || (count && !protected_regions)) return -10;
    rc=cnn_pipeline_status(&status); if(rc) return rc;
    if((status&13u) || *cnn_reg(CNN_LOAD_CONTROL) || *cnn_reg(CNN_LOAD_CONTROL+4)) return -11;
    for(uint32_t s=0;s<2;s++) {
        const cnn_frame *f=&layout[s];
        if(!f->cnn.count || f->cnn.count>0x0fffffffu ||
           (f->cnn.tiles&3u) || (f->configs.address&3u)) return -12;
        regions[n++]=(cnn_region){f->image.destination,f->image.bytes};
        regions[n++]=f->output;
        regions[n++]=(cnn_region){f->cnn.tiles,f->cnn.count*16u};
        regions[n++]=f->configs;
    }
    if(layout[0].cnn.buffer_a!=layout[1].cnn.buffer_a ||
       layout[0].cnn.buffer_b!=layout[1].cnn.buffer_b ||
       layout[0].cnn.capacity!=layout[1].cnn.capacity ||
       ((layout[0].cnn.buffer_a|layout[0].cnn.buffer_b|layout[0].cnn.capacity)&3u)) return -12;
    regions[n++]=(cnn_region){layout[0].cnn.buffer_a,layout[0].cnn.capacity};
    regions[n++]=(cnn_region){layout[0].cnn.buffer_b,layout[0].cnn.capacity};
    for(uint32_t i=0;i<count;i++) regions[n++]=protected_regions[i];
    regions[n++]=(cnn_region){CNN_LOAD_CONTROL,8};
    regions[n++]=(cnn_region){CNN_LOAD_DESCRIPTOR,20};
    for(uint32_t i=0;i<n;i++) {
        if(!cnn_region_valid(regions[i])) return -13;
        for(uint32_t j=0;j<i;j++) if(cnn_regions_overlap(regions[i],regions[j])) return -14;
    }
    for(uint32_t s=0;s<2;s++) {
        const cnn_frame *f=&layout[s];
        volatile uint32_t *tiles=cnn_reg(f->cnn.tiles);
        for(uint32_t i=0;i<f->cnn.count;i++) {
            uint32_t config=tiles[i*4],dst=tiles[i*4+1],bytes=tiles[i*4+2];
            if((config&3u) || !cnn_region_contains(f->configs,config,96) ||
               !cnn_region_contains(f->output,dst,bytes) || bytes>f->cnn.capacity) return -15;
            if(!cnn_region_contains((cnn_region){f->image.destination,f->image.bytes},
                                    cnn_reg(config)[1],1)) return -15;
        }
        q->frame[s]=*f; q->frame[s].state=CNN_FRAME_FREE;
    }
    q->loading=-1;q->running=-1;q->acknowledging=0;q->load_failed=0;q->error=0;
    q->submitted=0;q->started=0;
    return 0;
}
/* Enqueue only a FREE slot. Metadata, input, output and program stay owned until
   RESULT is explicitly released. No external CPU/bridge driver may bypass q. */
static inline int cnn_frame_submit(cnn_frames *q,uint32_t slot,
                                    uint32_t source,uint32_t crc32) {
    if(!q || slot>1 || q->error || q->frame[slot].state!=CNN_FRAME_FREE) return -16;
    cnn_frame *f=&q->frame[slot];
    if((uint64_t)source+f->image.bytes>0x100000000ull) return -17;
    f->image.source=source;f->image.crc32=crc32;
    f->sequence=q->submitted++;f->state=CNN_FRAME_QUEUED;
    return 0;
}
static inline int cnn_frame_release(cnn_frames *q,uint32_t slot) {
    if(!q || slot>1 || q->error || q->frame[slot].state!=CNN_FRAME_RESULT) return -18;
    cnn_memory_fence();q->frame[slot].state=CNN_FRAME_FREE;return 0;
}
/* One cooperative step; return to caller for useful CPU work between calls.
   Mailbox transactions have their existing bounded poll, not a CNN-job wait.
   Any error freezes ownership; timeout never implicitly frees live storage. */
static inline int cnn_frames_poll(cnn_frames *q) {
    uint32_t status;int rc;
    if(!q || q->error) return q ? q->error : -10;
    if(q->loading>=0) {
        status=*cnn_reg(CNN_LOAD_CONTROL+4);
        if(!q->acknowledging && (status&1u)) {
            q->load_failed=(status&2u)!=0;
            *cnn_reg(CNN_LOAD_CONTROL)=0;cnn_memory_fence();q->acknowledging=1;
        } else if(q->acknowledging && status==0 && *cnn_reg(CNN_LOAD_CONTROL)==0) {
            if(q->load_failed) return q->error=-19;
            cnn_memory_fence();q->frame[q->loading].state=CNN_FRAME_READY;
            q->loading=-1;q->acknowledging=0;
        }
    }
    if(q->running>=0) {
        rc=cnn_pipeline_status(&status);if(rc) return q->error=rc;
        if(status&12u) return q->error=-20;
        if((status&3u)==2u) {
            cnn_memory_fence();q->frame[q->running].state=CNN_FRAME_RESULT;q->running=-1;
        }
    }
    for(uint32_t s=0;s<2;s++) {
        cnn_frame *f=&q->frame[s];
        if(q->running<0 && f->state==CNN_FRAME_READY && f->sequence==q->started) {
            rc=cnn_pipeline_start(&f->cnn);if(rc) return q->error=rc;
            f->state=CNN_FRAME_RUNNING;q->running=(int)s;q->started++;
        }
    }
    if(q->loading<0) {
        int selected=-1;
        for(uint32_t s=0;s<2;s++) if(q->frame[s].state==CNN_FRAME_QUEUED &&
            (selected<0 || (int32_t)(q->frame[s].sequence-q->frame[selected].sequence)<0)) selected=(int)s;
        if(selected>=0) {
            cnn_frame *f=&q->frame[selected];
            if(*cnn_reg(CNN_LOAD_CONTROL) || *cnn_reg(CNN_LOAD_CONTROL+4)) return q->error=-11;
            volatile uint32_t *d=cnn_reg(CNN_LOAD_DESCRIPTOR);
            d[0]=0;d[1]=f->image.source;d[2]=f->image.destination;
            d[3]=f->image.bytes;d[4]=f->image.crc32;
            cnn_memory_fence();d[0]=0x31444c49u;cnn_memory_fence();
            *cnn_reg(CNN_LOAD_CONTROL)=1;
            f->state=CNN_FRAME_LOADING;q->loading=selected;
        }
    }
    return 0;
}
#endif
