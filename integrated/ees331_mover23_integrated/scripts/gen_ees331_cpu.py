"""Generate the real RV32I mailbox service for the unchanged soft CPU.

No C compiler/runtime, interrupt, mutable IMEM, or wait-state CPU extension.
All peripheral accesses fit the existing nine-word MMIO window.
"""
from pathlib import Path
import json
from gen_autoload_demo import Program

ROOT = Path(__file__).resolve().parents[1]


def generate():
    p = Program()
    def li(r,v): p.li(r,v)
    def rd(r,a): li(4,a);p.sw(1,4,8);p.lw(r,1,12)
    def wr(a,r): li(4,a);p.sw(1,4,8);p.sw(1,r,12)
    def const(a,v): li(5,v);wr(a,5)
    def eq(r,v,label): li(5,v);p.branch(0,r,5,label)
    def ne(r,v,label): li(5,v);p.branch(1,r,5,label)
    def mask(r,s,v): p.i(7,r,s,v,f'andi x{r}, x{s}, {v}')
    def idle():
        rd(10,0x1004);mask(5,10,2);p.branch(1,5,0,'busy')
    def ready(): p.branch(0,18,0,'not_ready')
    def fence(label,cmd=1):
        # x14 range start, x15 length. Command accepted now; poll completion.
        wr(0x2008,14);wr(0x200c,15);const(0x2004,cmd)
        li(17,20_000_000)
        p.label(label)
        rd(10,0x2000);mask(5,10,12);p.branch(1,5,0,'memory_error')
        mask(5,10,18);p.branch(0,5,0,label+'_done')
        p.i(0,17,17,-1,'addi x17, x17, -1')
        p.branch(1,17,0,label);p.jump('timeout')
        p.label(label+'_done')

    li(1,0x40000000);li(18,0)
    const(0x64,0x43505532)  # CPU_READY, not DDR_READY
    p.label('poll')
    p.lw(2,1,16);p.lw(5,1,20);p.branch(0,2,5,'poll')
    rd(3,0x10)
    for r,a in [(6,0x14),(7,0x18),(8,0x1c),(9,0x20)]:rd(r,a)
    for r in range(12,17):li(r,0)
    for op,label in [(1,'ddr_ready'),(2,'cfg_write'),(3,'cfg_commit'),(4,'start'),
                     (5,'frame'),(6,'result'),(7,'ack'),(8,'reset'),(9,'cache_cfg'),
                     (10,'status'),(11,'cache_read')]:eq(3,op,label)
    p.jump('bad_command')

    p.label('ddr_ready')
    idle();ne(6,0x44524459,'bad_command')
    rd(10,0x2000);mask(5,10,1);p.branch(0,5,0,'not_ready')
    mask(5,10,30);p.branch(1,5,0,'memory_error')
    li(18,1);p.jump('success')

    p.label('cfg_write');ready();idle()
    for off in [0x0c,0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x2c]:eq(6,off,'cfg_allowed')
    p.jump('bad_command')
    p.label('cfg_allowed')
    li(4,0x1000);p.emit((6<<20)|(4<<15)|(4<<7)|0x33,'add x4, x4, x6')
    p.sw(1,4,8);p.sw(1,7,12);p.jump('success')

    p.label('cfg_commit');ready();idle()
    eq(6,4,'commit_allowed');ne(6,8,'bad_command')
    p.label('commit_allowed');wr(0x1008,6);p.jump('check_cnn')

    p.label('start');ready();idle()
    rd(10,0x1004);mask(5,10,1);p.branch(0,5,0,'not_ready')
    const(0x1008,2);p.jump('check_cnn')

    p.label('frame');ready()
    li(5,4);p.branch(7,6,5,'bad_command')  # bgeu slot,4
    wr(0x1020,6);wr(0x102c,7)
    rd(10,0x1004);mask(5,10,16);p.branch(0,5,0,'busy')
    const(0x1008,16);p.jump('check_cnn')

    p.label('result');ready()
    rd(10,0x1004);mask(5,10,8);p.branch(1,5,0,'cnn_error')
    mask(5,10,32);p.branch(0,5,0,'again')
    rd(13,0x1030);rd(14,0x1034);rd(15,0x1038);rd(16,0x1054)
    fence('result_fence')
    p.jump('success')

    p.label('ack');ready()
    rd(10,0x1004);mask(5,10,32);p.branch(0,5,0,'again')
    rd(5,0x1030);p.branch(1,5,6,'bad_token')
    rd(5,0x1054);p.branch(1,5,7,'bad_token')
    wr(0x104c,6);wr(0x1050,7);const(0x1008,32);p.jump('check_cnn')

    p.label('reset');ready();idle()
    li(14,0);li(15,0x01000000);fence('reset_fence',2)
    const(0x1008,1);rd(13,0x1054);p.jump('success')

    p.label('cache_cfg');ready();idle()
    eq(6,0x10,'cache_allowed');ne(6,0x14,'bad_command')
    p.label('cache_allowed')
    li(4,0x2000);p.emit((6<<20)|(4<<15)|(4<<7)|0x33,'add x4, x4, x6')
    p.sw(1,4,8);p.sw(1,7,12);p.jump('success')

    p.label('status')
    rd(13,0x1004);rd(14,0x1040);rd(15,0x2000);rd(16,0x1054);p.jump('success')

    p.label('cache_read')
    mask(5,6,3);p.branch(1,5,0,'bad_command');li(5,0x3c);p.branch(7,6,5,'bad_command')
    li(4,0x2000);p.emit((6<<20)|(4<<15)|(4<<7)|0x33,'add x4, x4, x6')
    p.sw(1,4,8);p.lw(13,1,12);p.jump('success')

    p.label('check_cnn')
    rd(10,0x1004);mask(5,10,8);p.branch(1,5,0,'cnn_error')
    p.label('success');li(12,0);p.jump('reply')
    for label,code in [('bad_command',1),('again',2),('busy',3),('not_ready',4),
                       ('cnn_error',5),('memory_error',6),('timeout',7),('bad_token',8)]:
        p.label(label);li(12,code);p.jump('reply')
    p.label('reply')
    wr(0x50,12)
    for r,a in [(13,0x54),(14,0x58),(15,0x5c),(16,0x60)]:wr(a,r)
    p.sw(1,2,20)  # publish ACK last, after the complete response
    p.jump('poll')
    p.resolve()
    out=ROOT/'firmware/ees331_cpu';out.mkdir(parents=True,exist_ok=True)
    words=[w for w,_ in p.code]
    if len(words)>2048:raise RuntimeError('8KiB ROM exceeded')
    (out/'program.mem').write_text(''.join(f'{w:08x}\n' for w in words+[0x13]*(2048-len(words))),encoding='ascii')
    labels={v:k for k,v in p.labels.items()}
    lines=['# Real RV32I mailbox service. Bytes shown exclude NOP padding to 8KiB.']
    for i,(w,comment) in enumerate(p.code):
        if i*4 in labels:lines.append(labels[i*4]+':')
        lines.append(f'{i*4:04x}  {w:08x}  {comment}')
    (out/'program.lst').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'instructions':len(words),'used_bytes':len(words)*4,
        'rom_bytes':8192,'entry':0,'stack_bytes':0,'uses_dmem':False,
        'cpu_control_datapath_modified':False},indent=2)+'\n',encoding='utf-8')
    print(f'RV32I service: {len(words)} instructions, {len(words)*4}/8192 bytes')

if __name__=='__main__':generate()
