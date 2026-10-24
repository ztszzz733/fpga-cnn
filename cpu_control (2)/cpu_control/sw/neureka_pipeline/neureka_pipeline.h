#ifndef NEUREKA_PIPELINE_H
#define NEUREKA_PIPELINE_H
#include <stdint.h>
/* Existing zero-wait CPU aperture. Target addresses are sent through this mailbox. */
#ifndef CNN_MAILBOX
#define CNN_MAILBOX 0x40000000u
#endif
#define CNN_VECTOR (CNN_MAILBOX + 0x40000u)
/* Hardware patches native config word 2 to A/B. Count is bytes for INT8 program mode 0. */
typedef struct { uint32_t config, destination, bytes, mode; } cnn_tile;
typedef struct { uint32_t tiles, count, buffer_a, buffer_b, capacity, serial; } cnn_pipeline_job;
static inline volatile uint32_t *cnn_reg(uint32_t address) {
    return (volatile uint32_t *)(uintptr_t)address;
}
static inline int cnn_target(uint32_t address,uint32_t data,int write,uint32_t *value) {
    volatile uint32_t *mb=cnn_reg(CNN_MAILBOX);
    uint32_t budget=1000000u;
    if(mb[3]&1u) return -1;
    mb[0]=address;mb[1]=data;mb[2]=write?1u:2u;
    while(mb[3]&1u) if(--budget==0) return -2;
    if(mb[3]&4u) return -3;
    if(value) *value=mb[4];
    return 0;
}
static inline int cnn_pipeline_status(uint32_t *status) {
    return cnn_target(CNN_MAILBOX+4,0,0,status);
}
static inline int cnn_pipeline_load_program(const uint32_t *words,uint32_t count) {
    uint32_t status;int rc;
    if(!words || !count || count>4096) return -4;
    rc=cnn_pipeline_status(&status);if(rc) return rc;
    if(status&5u) return -5;
    rc=cnn_target(CNN_VECTOR,0,0,&status);if(rc) return rc;
    if(status&5u) return -5;
    for(uint32_t i=0;i<count;i++) {
        rc=cnn_target(CNN_VECTOR+0x1000u+4*i,words[i],1,0);if(rc) return rc;
    }
    return 0;
}
static inline int cnn_pipeline_start(const cnn_pipeline_job *job) {
    uint32_t status;int rc=cnn_pipeline_status(&status);if(rc) return rc;
    if(!job || (status&5u)) return -5;
    const uint32_t values[6]={job->tiles,job->count,job->buffer_a,job->buffer_b,job->capacity,job->serial&1u};
    /* Caller owns SRAM input, packed weights, native configs, output and slots
       until completion. Keep all ranges disjoint except deliberate input halo. */
    for(uint32_t i=0;i<6;i++) {
        rc=cnn_target(CNN_MAILBOX+8+4*i,values[i],1,0);if(rc) return rc;
    }
    __asm__ volatile ("fence" ::: "memory");
    return cnn_target(CNN_MAILBOX,1,1,0);
}
static inline int cnn_pipeline_wait(uint32_t poll_budget) {
    while(poll_budget--) {
        uint32_t status;int rc=cnn_pipeline_status(&status);if(rc) return rc;
        if(status&12u) return -6;
        if(status&2u) { __asm__ volatile ("fence" ::: "memory");return 0; }
    }
    return -2; /* Timeout does not release buffers; hardware may still be busy. */
}
#endif
