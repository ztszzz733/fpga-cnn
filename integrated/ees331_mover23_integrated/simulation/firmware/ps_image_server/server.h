#ifndef EES331_IMAGE_SERVER_H
#define EES331_IMAGE_SERVER_H
#include <stdint.h>
#include <stddef.h>
#define EES331_DDR_BASE 0x10000000u
#define EES331_DDR_BYTES 0x01000000u
#define EES331_MAILBOX_BASE 0x40000000u
#define EES331_MAX_PACKET 256u
enum { RPC_CAPS=0, RPC_MODEL_BEGIN=1, RPC_MODEL_END=2, RPC_CFG_WRITE=3,
 RPC_TEMPLATE_COMMIT=4, RPC_DEFINE=5, RPC_START=6, RPC_FRAME=7,
 RPC_RESULT=8, RPC_ACK=9, RPC_STATUS=10, RPC_BATCH_RESET=11 };
enum { S_OK=0,S_CRC=1,S_COMMAND=2,S_RANGE=3,S_ACCESS=4,S_TIMEOUT=5,
 S_STATE=6,S_CPU=7,S_TOKEN=8 };
typedef struct {
 uint32_t input,workspace,workspace_bytes,id,length,received,epoch,result_read;
 uint8_t defined,committed,result_seen,acked;
} ees331_frame;
typedef struct {
 volatile uint8_t *ddr;
 void *opaque;
 int (*cpu)(void*,uint32_t,const uint32_t[4],uint32_t[4]);
 void (*to_device)(void*,uint32_t,uint32_t);
 void (*from_device)(void*,uint32_t,uint32_t);
 ees331_frame frame[4];
 uint32_t model_end,model_received,model_version,frames,templates;
 uint8_t model_upload,model_sealed,running,transport_fault;
} ees331_server;
uint32_t ees331_crc32(const uint8_t*,size_t);
void ees331_server_init(ees331_server*,volatile uint8_t*);
/* op1 write/op2 read preserve IMIO v1. op3 is a task RPC; address is RPC_*.
 * Caller checks packet CRC first. Response payload is at most 256 bytes. */
uint8_t ees331_handle(ees331_server*,uint8_t,uint32_t,const uint8_t*,uint16_t,
                     uint8_t*,uint16_t*);
#endif
