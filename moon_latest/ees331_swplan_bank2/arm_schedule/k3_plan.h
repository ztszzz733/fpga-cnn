#ifndef EES331_K3_PLAN_H
#define EES331_K3_PLAN_H
#include <stdint.h>
#define EES331_K3_PLANNED 0x80000000u
#define EES331_K3_INPUT_WORD 0x100u
#define EES331_K3_WEIGHT_WORD 0x200u
#define EES331_K3_REUSE 0x400u
#define EES331_K3_WEIGHT_BYTES (9u * 512u)

/* Command words 13/14 belong to frame relocation, not this plan. */
static inline int ees331_validate_k3(const uint32_t r[20])
{
    if (r[0] != 0u) return 1;
    const uint32_t ci=r[6], w=r[7], h=r[8], co=r[9], stride=r[10], flags=r[11];
    if (!(flags&EES331_K3_PLANNED) || (flags&~0x80000701u) ||
        !ci || ci>512u || !co || co>512u || w<3u || h<3u || w>65535u || h>65535u ||
        (stride!=1u && stride!=2u) || ((flags&1u) && ci!=co) || (r[3]&3u)) return 0;
    uint64_t row=(uint64_t)w*ci, input=row*h;
    uint64_t per=9u*((flags&1u)?1u:ci), weights=per*co;
    uint64_t output=(uint64_t)((w-3u)/stride+1u)*((h-3u)/stride+1u)*co*4u;
    if (row>UINT32_MAX || input>UINT32_MAX || weights>UINT32_MAX || output>UINT32_MAX ||
        r[4]!=row || r[5]!=per || r[12]!=input || r[15]!=weights) return 0;
    uint32_t loaded=(flags&EES331_K3_REUSE)?r[15]:r[5];
    if (!loaded || loaded>EES331_K3_WEIGHT_BYTES) return 0;
    if ((flags&EES331_K3_INPUT_WORD) && ((r[1]&3u) || (ci&3u))) return 0;
    if ((flags&EES331_K3_WEIGHT_WORD) && ((r[2]&3u) || (loaded&3u))) return 0;
    return 1;
}
#endif
