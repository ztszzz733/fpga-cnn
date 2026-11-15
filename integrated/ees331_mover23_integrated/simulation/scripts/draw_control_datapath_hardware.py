"""Draw an audited RTL wiring sheet from production SV and an existing VCD.

Only documentation artifacts are written. No RTL or simulation data is changed.
"""
from __future__ import annotations
import hashlib
import json
import re
import textwrap
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DP = ROOT / 'build/datapath_review/20260917_211827'
RUN = ROOT / 'build/runs/20260917_212107_968626_real_datapath_review'
OUT = ROOT / 'docs/figures/control_datapath_hardware'
ZIP = Path('D:/QQ/face_recognition_soc_datapath_complete.zip')
W = 4800
BLUE, GREEN, PURPLE, ORANGE = '#1769aa', '#16784b', '#7850a2', '#b26b16'
INK, MUTED, LINE = '#152b42', '#526578', '#cbd7e1'

def clean(s):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)

def declarations(s):
    result = {}
    pat = r'\b(?:(input|output)\s+)?(logic|(?:cpu_control_pkg::)?decode_t)\s*(\[\d+:\d+\])?\s*([^;()]+?)(?=\s*(?:;|\)|\binput\b|\boutput\b))'
    for m in re.finditer(pat, clean(s)):
        direction, typ, bus, names = m.groups()
        width = 28 if typ.endswith('decode_t') else 1
        if bus:
            a,b = map(int, bus[1:-1].split(':')); width = abs(a-b)+1
        for name in names.split(','):
            name = name.strip().rstrip(',').strip()
            if not name: continue
            # The regfile array is implemented even though XSim omits it from VCD.
            array = re.fullmatch(r'(\w+)\s*\[(\d+):(\d+)\]', name)
            if array:
                result[array[1]] = dict(direction=direction, width=width, count=abs(int(array[2])-int(array[3]))+1)
            elif re.fullmatch(r'\w+', name):
                result[name] = dict(direction=direction, width=width)
    return result

def read_vcd(p):
    stack=[]; result={}
    with p.open(encoding='utf-8') as f:
        for line in f:
            t=line.split()
            if not t: continue
            if t[0]=='$scope': stack.append(t[2])
            elif t[0]=='$upscope': stack.pop()
            elif t[0]=='$var':
                result['.'.join(stack+[t[4]])] = dict(kind=t[1],width=int(t[2]),code=t[3])
            elif t[0]=='$enddefinitions': break
    return result

files = list((DP/'rtl/cpu_datapath').glob('*.sv'))+list((ROOT/'rtl/cpu_control').glob('*.sv'))+list((RUN/'mixed/models').glob('*.sv'))
modules={}
for p in files:
    s=p.read_text(encoding='utf-8'); name=re.search(r'\bmodule\s+(\w+)',clean(s))[1]
    decl=declarations(s)
    modules[name]=dict(path=p,text=s,decl=decl,ports={k:v for k,v in decl.items() if v['direction']})
vcd=read_vcd(RUN/'mixed/waves/real_control_datapath.vcd')
common=set(modules['cpu_control']['ports'])
netinfo={}; drivers=defaultdict(list); sinks=defaultdict(list); instances=[]; combos=[]

def key(scope,n):
    base=n.split('[')[0].split('.')[0]
    if base in modules['cpu_datapath']['ports'] or base in common: return 'G.'+base
    return scope+'.'+base

def add_net(scope,n,width=None):
    k=key(scope,n)
    if width is None: width=modules['cpu_control' if scope=='C' else 'cpu_datapath']['decl'][n]['width']
    if k in netinfo: assert netinfo[k]['width']==width,(k,width,netinfo[k])
    netinfo[k]=dict(width=width)
    return k

for scope,mod in [('D','cpu_datapath'),('C','cpu_control')]:
    for n,d in modules[mod]['decl'].items(): add_net(scope,n,d['width'])

def parse_instances(scope,mod):
    s=clean(modules[mod]['text'])
    leaf_types='|'.join(re.escape(n) for n in modules if n not in ('cpu_datapath','cpu_control'))
    pat=rf'^\s*({leaf_types})\s*(?:#\s*(\((?:[^()]|\([^()]*\))*\))\s*)?(u_\w+)\s*\((.*?)\)\s*;'
    for m in re.finditer(pat,s,re.S|re.M):
        typ,params,name,body=m.groups()
        if typ not in modules: continue
        maps=re.findall(r'\.(\w+)\s*\(([^()]*)\)',body)
        ports=modules[typ]['ports']; assert set(dict(maps))==set(ports),(typ,set(ports)-set(dict(maps)))
        inst=dict(id=scope+'.'+name,type=typ,scope=scope,name=name,ports=[],params=params or '')
        for pin,net in maps:
            net=net.strip(); d=ports[pin]; k=None
            if re.match(r'^\w+(?:\[\d+:\d+\])?$',net):
                k=key(scope,net); assert k in netinfo,(name,pin,net)
                width=netinfo[k]['width']
                if '[' in net:
                    a,b=map(int,re.search(r'\[(\d+):(\d+)\]',net).groups()); width=abs(a-b)+1
                assert width==d['width'],(name,pin,net,width,d)
                (drivers if d['direction']=='output' else sinks)[k].append(inst['id']+'.'+pin+(' ← '+net[net.index('['):] if '[' in net else ''))
            else: assert re.match(r"^\d+'[bhdo][0-9a-f_]+$",net,re.I),(name,pin,net)
            inst['ports'].append(dict(pin=pin,net=net,key=k,**d))
        instances.append(inst)

parse_instances('D','cpu_datapath'); parse_instances('C','cpu_control')

def combo(scope,name,ins,outs,formula):
    item=dict(id=scope+'.'+name,scope=scope,type='RTL组合逻辑',formula=formula,ports=[])
    for direction,names in [('input',ins.split()),('output',outs.split())]:
        for n in names:
            k=key(scope,n); assert k in netinfo,(name,n)
            item['ports'].append(dict(pin=n,net=n,key=k,direction=direction,width=netinfo[k]['width']))
            (drivers if direction=='output' else sinks)[k].append(item['id']+'.'+n)
    combos.append(item)

# Continuous assigns are read from source, rather than retyped.
for scope,mod in [('D','cpu_datapath'),('C','cpu_control')]:
    s=clean(modules[mod]['text'])
    for lhs,rhs in re.findall(r'\bassign\s+(\w+)\s*=\s*(.*?);',s,re.S):
        ins=[]
        for token in re.findall(r'\b[A-Za-z_]\w*\b',rhs):
            if key(scope,token) in netinfo and token not in ins: ins.append(token)
        combo(scope,'assign_'+lhs,' '.join(ins),lhs,re.sub(r'\s+',' ',rhs))

combo('D','MUX_PC','pc_sel pc4_seq branch_target jalr_target','next_pc','pc_sel: 0→PC+4; 1→PC+imm; 2→(rs1+imm)&~1')
combo('D','MUX_MEM_FORWARD','wb_sel_m alu_result_m pc4_m','mem_forward_m','wb_sel_m: 0→ALU; 2→PC+4; 其它→0；不前递 Load 地址')
for short,out,reg,sel in [('A','src1_fwd_e','rd1_e','fwd_a'),('B','src2_fwd_e','rd2_e','fwd_b'),('STORE','store_data_fwd_e','rd2_e','fwd_store')]:
    combo('D','MUX_FWD_'+short,f'{sel} {reg} wb_data_w mem_forward_m',out,f'{sel}: 0→寄存器; 1→WB; 2→MEM非Load')
combo('D','MUX_ALU_A','alu_src_a_sel_e src1_fwd_e pc_e','alu_a_e','0→前递rs1; 1→PC; 2→0')
combo('D','MUX_ALU_B','alu_src_b_sel_e src2_fwd_e imm_e','alu_b_e','0→前递rs2; 1→立即数')
combo('D','MUX_LOAD','legal_sram_load_m sram_load_data_m legal_mmio_load_m mmio_ready mmio_rdata','read_data_m','合法SRAM→LSU结果; 合法MMIO且ready→MMIO数据; 其它→0')
combo('D','MUX_WB','wb_sel_w alu_result_w read_data_w pc4_w','wb_data_w','0→ALU; 1→Load; 2→PC+4')
combo('C','SAFE_DECODE','rst_n valid_d legal_main legal_alu decoded_main decoded_alu','decoded_safe illegal_d','rst_n & valid_d & legal_main & legal_alu →控制字；否则全0')

# Models are boundary objects, not implemented production hardware.
for typ,name,mapping in [
    ('imem_model','u_imem',dict(clk='clk',re='imem_re',addr='imem_addr',rdata='imem_rdata')),
    ('dmem_model','u_dmem',dict(clk='clk',re='dmem_re',we='dmem_we',wstrb='dmem_wstrb',addr='dmem_addr',wdata='dmem_wdata',rdata='dmem_rdata')),
    ('cnn_mmio_stub','u_mmio',dict(clk='clk',rst_n='rst_n',addr='mmio_addr',wdata='mmio_wdata',re='mmio_re',we='mmio_we',rdata='mmio_rdata',ready='mmio_ready'))]:
    inst=dict(id='T.'+name,type=typ,scope='T',name=name,ports=[],params='')
    assert set(mapping)==set(modules[typ]['ports'])
    for pin,n in mapping.items():
        d=modules[typ]['ports'][pin]; k=key('D',n); assert netinfo[k]['width']==d['width']
        (drivers if d['direction']=='output' else sinks)[k].append(inst['id']+'.'+pin)
        inst['ports'].append(dict(pin=pin,net=n,key=k,**d))
    instances.append(inst)
drivers['G.clk'].append('TB时钟源（仿真）'); drivers['G.rst_n'].append('TB复位源（仿真）')

for k in netinfo:
    assert len(drivers[k])==1,(k,'drivers',drivers[k])
netids={k:f'N{i:03}' for i,k in enumerate(sorted(netinfo),1)}

# Verify the extracted production sources against the user's actual archive.
zip_checks=[]
with zipfile.ZipFile(ZIP) as z:
    for mod,data in modules.items():
        p=data['path']
        if DP not in p.parents: continue
        relative=p.relative_to(DP).as_posix()
        candidates=[n for n in z.namelist() if n==relative or n.endswith('/'+relative)]
        assert len(candidates)==1,(relative,candidates)
        assert z.read(candidates[0])==p.read_bytes(),relative
        zip_checks.append(relative)

# Waveform scope/width validation for all module pins and all top-level nets.
validated=[]
for scope,mod,vscope in [('D','cpu_datapath','tb_cpu_datapath.dut'),('C','cpu_control','tb_cpu_datapath.u_control')]:
    for n,d in modules[mod]['decl'].items():
        full=vscope+'.'+n; assert full in vcd,full
        assert vcd[full]['width']==d['width'],(full,vcd[full],d)
        validated.append(full)
for inst in instances:
    prefix={'D':'tb_cpu_datapath.dut.','C':'tb_cpu_datapath.u_control.','T':'tb_cpu_datapath.'}[inst['scope']]+inst['name']
    for p in inst['ports']:
        full=prefix+'.'+p['pin']; assert full in vcd,full
        assert vcd[full]['width']==p['width'],(full,vcd[full],p)
        validated.append(full)

internal=[]
for inst in instances:
    if inst['scope']=='T': continue
    prefix={'D':'tb_cpu_datapath.dut.','C':'tb_cpu_datapath.u_control.'}[inst['scope']]+inst['name']
    rows=[]
    for n,d in modules[inst['type']]['decl'].items():
        if d['direction']: continue
        full=prefix+'.'+n
        if 'count' in d:
            rows.append((n,f"{d['count']} × {d['width']} bit（已实现，VCD未展开）"))
        else:
            assert full in vcd,full
            assert vcd[full]['width']==d['width'],(full,d,vcd[full])
            validated.append(full); rows.append((n,f"{d['width']} bit"))
    if rows: internal.append((inst,rows))

def internal_wiring(inst,rows):
    """Read internal-node data inputs and the module's selection conditions."""
    mod=modules[inst['type']]; source=clean(mod['text']); decl=mod['decl']
    result=[]
    for n,width in rows:
        expressions=re.findall(r'\b'+re.escape(n)+r'(?:\[[^\]]+\])?\s*(?:<=|=(?!=))\s*(.*?);',source,re.S)
        refs=[]
        for expr in expressions:
            for token in re.findall(r'\b[A-Za-z_]\w*\b',expr):
                if token in decl and token!=n and token not in refs: refs.append(token)
        inputs=' + '.join(f"{r}[{decl[r]['width']}]" for r in refs) or '常量/按条件赋值'
        target=f"{n}[{decl[n]['width']}]"+(' ×32' if n=='regs' else '')
        result.extend(textwrap.wrap(inputs+' → '+target,95))
    conditions=[]
    for m in re.finditer(r'\b(?:if|case)\s*\(',source):
        start=m.end(); end=start; depth=1
        while depth and end<len(source):
            if source[end]=='(': depth+=1
            elif source[end]==')': depth-=1
            end+=1
        condition=source[start:end-1]
        for token in re.findall(r'\b[A-Za-z_]\w*\b',condition):
            if token in decl and token not in conditions: conditions.append(token)
    if 'always_ff' in source and 'clk' in decl and 'clk' not in conditions: conditions.insert(0,'clk')
    result.extend(textwrap.wrap('if/case/时序选择条件：'+' / '.join(f"{n}[{decl[n]['width']}]" for n in conditions),95))
    return result

production_wave_nodes={n for n,d in vcd.items() if n.startswith(('tb_cpu_datapath.dut.','tb_cpu_datapath.u_control.')) and d['kind']!='parameter'}
excluded_wave_nodes={'tb_cpu_datapath.dut.u_regfile.i': 'for循环integer，仿真展开变量，不是寄存器堆硬件连线'}
assert production_wave_nodes-set(validated)==set(excluded_wave_nodes),production_wave_nodes-set(validated)

OUT.mkdir(parents=True,exist_ok=True)

class Sheet:
    def __init__(self): self.ops=[]; self.y=0
    def rect(self,x,y,w,h,fill='#ffffff',stroke=LINE,r=14): self.ops.append(('rect',(x,y,w,h,fill,stroke,r)))
    def text(self,x,y,s,size=24,color=INK,bold=False): self.ops.append(('text',(x,y,str(s),size,color,bold)))
    def line(self,points,color=BLUE,width=3,arrow=False,dash=False): self.ops.append(('line',(points,color,width,arrow,dash)))
    def section(self,y,n,title,sub):
        self.rect(50,y,W-100,105,'#eaf0f6',None,10); self.text(80,y+12,n+'  '+title,36,INK,True); self.text(80,y+65,sub,23,MUTED)
        return y+130
    def save(self,path,height):
        im=Image.new('RGB',(W,height),'white'); draw=ImageDraw.Draw(im)
        fonts={}
        def font(size,bold):
            k=(size,bold)
            if k not in fonts: fonts[k]=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc' if bold else 'C:/Windows/Fonts/msyh.ttc',size)
            return fonts[k]
        svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">', '<title>Control + Datapath 全部已实现RTL硬件与波形连线</title>', '<desc>主通路、全部实例端口、全部顶层组合逻辑、逐网驱动与扇出、模块内部波形状态。位宽按RTL与VCD核实。</desc>', '<rect width="100%" height="100%" fill="white"/>']
        for typ,a in self.ops:
            if typ=='rect':
                x,y,w,h,fill,stroke,r=a
                draw.rounded_rectangle((x,y,x+w,y+h),radius=r,fill=fill,outline=stroke,width=2)
                svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="2"/>')
            elif typ=='text':
                x,y,s,size,color,bold=a; draw.text((x,y),s,font=font(size,bold),fill=color)
                svg.append(f'<text x="{x}" y="{y+size}" font-family="Microsoft YaHei,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(s)}</text>')
            else:
                pts,color,width,arrow,dash=a
                if dash:
                    # Dash only the model-boundary wires in SVG; PNG uses thin lines.
                    pass
                draw.line(pts,fill=color,width=width)
                svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="none" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="10 8"' if dash else '')+'/>')
                if arrow:
                    x,y=pts[-1]; ax,ay=pts[-2]; dx=x-ax; dy=y-ay; norm=(dx*dx+dy*dy)**.5
                    dx/=norm; dy/=norm
                    triangle=[(x,y),(x-13*dx+6*dy,y-13*dy-6*dx),(x-13*dx-6*dy,y-13*dy+6*dx)]
                    draw.polygon(triangle,fill=color)
                    svg.append(f'<polygon points="{" ".join(f"{a},{b}" for a,b in triangle)}" fill="{color}"/>')
        svg.append('</svg>'); path.with_suffix('.svg').write_text('\n'.join(svg),encoding='utf-8')
        im.save(path.with_suffix('.png'),optimize=True)
        return im

s=Sheet()
s.text(65,32,'Control + Datapath｜全部已实现硬件与波形连线',56,INK,True)
s.text(65,112,'依据：实际 Datapath ZIP + 本方 Control RTL + 2026-09-17 真实连接 mixed VCD；绘图日期 2026-09-18',27,MUTED)
s.text(65,158,'层级：RTL模块 / 流水寄存器 / 寄存器堆 / 组合运算与MUX；本图不是综合后的门级网表。所有箭头按信号流向。',27,MUTED)
s.text(65,206,'蓝色 D = Datapath；绿色 C = Control；橙色 T = 仿真边界。相同 N编号 = 同一根网络，分布端点电气相连。',27,MUTED)
s.text(65,254,f'核对：{len(netinfo)} 根顶层网络；{len(instances)-3} 个生产子模块实例；{len(combos)} 组顶层组合逻辑；{len(validated)} 项波形声明。',27,INK,True)
y=s.section(320,'01','主通路与硬件布局','主通路图用于定位；下面的端子图与逐网展开图完整列出每根信号，不用省略号代替接线。')

def block(x,y,w,h,title,lines,color=BLUE):
    s.rect(x,y,w,h,'#f5f9fc',color,12); s.text(x+18,y+12,title,28,color,True)
    for i,line in enumerate(lines): s.text(x+18,y+59+i*34,line,23,INK)

# Five datapath stage columns and a separate control lane.
xs=[80,1020,1960,2900,3840]; cw=840
for x,title in zip(xs,['IF 取指','ID 译码','EX 执行','MEM 访存','WB 写回']): s.text(x,y,title,35,INK,True)
base=y+62
block(xs[0],base,cw,260,'u_pc + PC选择网络',['pc_q / next_pc [32]','PC+4 / PC+imm / JALR目标 [32]','pc_en [1]，pc_sel [2]','JALR目标最低位强制清0'])
block(xs[0],base+315,cw,300,'u_fetch : fetch_adapter',['同步请求配对 + 暂停响应缓存','request_pc / imem_addr [32]','imem_re / fetch_valid [1]','fetch_instr / fetch_pc / fetch_pc4 [32]','req / buffer 状态见05'])
block(xs[1],base,cw,200,'u_if_id : IF/ID寄存器',['instr_d / pc_d / pc4_d [32]','valid_d / en / flush [1]'])
block(xs[1],base+255,cw,230,'u_regfile + u_imm_gen',['32×32 寄存器，x0读为0','rs1_d / rs2_d / rd_d [5]','rd1_d / rd2_d / imm_d [32]','WB→ID 写回旁路'])
block(xs[1],base+540,cw,200,'u_id_ex : ID/EX寄存器',['数据 [32] / 寄存器号 [5]','译码控制字跨级保存','flush 插入气泡；完整字段见02'])
block(xs[2],base,cw,220,'前递MUX + ALU源MUX',['A / B / Store 三路前递 [32]','fwd_a / fwd_b / fwd_store [2]','ALU源选择 alu_src_*_sel_e [2]'])
block(xs[2],base+275,cw,235,'u_alu + 三种比较器',['alu_a_e / alu_b_e / result [32]','alu_ctrl_e [4]；10种ALU运算','cmp_eq_e / lt_e / ltu_e [1]','比较使用前递后的rs1/rs2'])
block(xs[2],base+565,cw,230,'u_addr_e + u_lsu_e',['地址译码 / 写数据移位 / 对齐','dmem_addr / wdata [32]，wstrb [4]','re / we / 对齐合法性 [1]','SRAM请求在 EX→MEM 边沿接受'])
block(xs[3],base,cw,220,'u_ex_mem : EX/MEM寄存器',['alu_result_m / write_data_m [32]','pc4_m [32]，rd_m [5]','valid / 读写使能 [1] + 类型控制'])
block(xs[3],base+275,cw,270,'u_addr_m + u_lsu_m',['SRAM字节/半字选择 + 符号扩展','MMIO 仅合法对齐 LW / SW','地址 / 数据 [32]，re / we [1]','load返回选择MUX [32]','MEM前递MUX [32]（非Load）'])
block(xs[3],base+600,cw,195,'u_mem_wb : MEM/WB寄存器',['Load / ALU / PC+4 三候选 [32]','rd_w [5]，wb_sel_w [2]','valid_w / regwrite_w [1]'])
block(xs[4],base,cw,250,'写回MUX + 寄存器写使能',['wb_sel_w [2] → wb_data_w [32]','0=ALU；1=Load；2=PC+4','rf_we=valid_w & regwrite_w','         & (rd_w != 0)','waddr [5] → u_regfile'])
# Route the actual stage boundaries; the bend stays in the column gutter.
for i,sy,ty in [(0,base+465,base+100),(1,base+640,base+100),(2,base+390,base+100),(3,base+700,base+120)]:
    gutter=xs[i]+cw+50
    s.line([(xs[i]+cw,sy),(gutter,sy),(gutter,ty),(xs[i+1],ty)],BLUE,4,True)
    s.text(gutter+8,min(sy,ty)+18,'[32]',20,BLUE)
for col,sy,ty in [(0,base+260,base+315),(1,base+200,base+255),(1,base+485,base+540),(2,base+220,base+275),(2,base+510,base+565),(3,base+220,base+275),(3,base+545,base+600)]:
    xx=xs[col]+cw/2
    s.line([(xx,sy),(xx,ty)],BLUE,3,True)
# Memory boundary at the right, connected back by named terminals.
block(xs[4],base+310,cw,190,'T.u_imem｜同步指令存储器模型',['imem_addr / rdata [32]','imem_re / clk [1]'],ORANGE)
block(xs[4],base+550,cw,190,'T.u_dmem｜同步数据存储器模型',['dmem_addr / wdata / rdata [32]','dmem_wstrb [4]；re / we / clk [1]'],ORANGE)
block(xs[4],base+790,cw,190,'T.u_mmio｜CNN MMIO stub',['mmio_addr / wdata / rdata [32]','re / we / ready / rst_n / clk [1]'],ORANGE)
# Feedback is a real 32-bit writeback bus, with a 5-bit destination and 1-bit enable.
s.line([(xs[4]+cw/2,base+250),(xs[4]+cw/2,base+280),(4750,base+280),(4750,base+1005),(1905,base+1005),(1905,base+365),(xs[1]+cw,base+365)],PURPLE,3,True)
s.text(1950,base+1010,'WB→ID：wb_data_w [32] + rd_w [5] + rf_we [1]；WB数据同时进入EX三路前递MUX',23,PURPLE)
cy=base+1045
block(80,cy,1440,245,'C.u_main_decoder + C.u_alu_decoder',['instr_d [32]；opcode [7] / funct3 [3] / funct7 [7]','decoded_main [28] + decoded_alu [4] + legal [1]','SAFE_DECODE → ID控制字段；经ID/EX进入执行级','Control无跨拍状态；clk只保留接口'],GREEN)
block(1620,cy,1440,245,'C.u_hazard_unit',['D/E/M/W valid [1] + rs/rd [5] + 源使用 [1]','Load-use → load_use [1]；M优先W前递','raw_fwd_a / b / store [2] →复位限定→ fwd_* [2]','operand_unready [1] 为诊断输出，不参与暂停'],GREEN)
block(3160,cy,1440,245,'C.u_branch_control + C.u_pipeline_control',['EX分支类型 [3] / jump [2] / 三比较标志 [1]','redirect [1] / redirect_sel [2] → pc_sel [2]','pc_en / if_id_en / if_id_flush / id_ex_flush [1]','reset > redirect > load-use > 正常'],GREEN)
s.line([(500,cy),(500,cy-35),(1440,cy-35),(1440,base+740)],GREEN,3,True)
s.text(530,cy-72,'ID控制字段 → ID/EX（每字段位宽见02）',23,GREEN)
s.line([(2390,cy),(2390,base+220)],GREEN,3,True)
s.text(2410,base+855,'fwd_a/b/store [2]',23,GREEN)
s.text(80,cy+282,'公共连线：clk [1] / rst_n [1]；所有有状态生产模块使用上升沿、同步低有效复位。Control的rst_n为组合安全限定。',25,MUTED)
s.text(80,cy+328,'未在生产RTL实现：CNN计算核心、DMA、双口共享SRAM、九寄存器正式硬件桥。mul_busy [1] 实际绑0，无乘法器。',25,ORANGE)
overview_h=cy+390
overview_ops=list(s.ops)

def terminal_card(item,x,y,w=1510):
    ins=[p for p in item['ports'] if p['direction']=='input']; outs=[p for p in item['ports'] if p['direction']=='output']
    rows=max(len(ins),len(outs),1); h=105+rows*65
    color={'C':GREEN,'D':BLUE,'T':ORANGE}[item['scope']]
    s.rect(x,y,w,h,'#ffffff',LINE,12)
    s.text(x+18,y+10,item['id']+'  |  '+item['type'],27,color,True)
    s.text(x+18,y+52,'网络名 [位宽]；下行=实例端口名；N编号跨图直接相连',21,MUTED)
    bx=x+690; bw=130
    s.rect(bx,y+90,bw,rows*65+3,'#eef4f8',color,10)
    for idx,ports in enumerate([ins,outs]):
        for r,p in enumerate(ports):
            yy=y+97+r*65
            label=f"{netids[p['key']] if p['key'] else '常量'} {p['net']} [{p['width']}]"
            if idx==0:
                s.text(x+18,yy,label,22); s.text(x+18,yy+30,'→ .'+p['pin'],20,MUTED)
                s.line([(bx-56,yy+17),(bx,yy+17)],color,3,True)
            else:
                s.line([(bx+bw,yy+17),(bx+bw+56,yy+17)],color,3,True)
                s.text(bx+bw+72,yy,label,22); s.text(bx+bw+72,yy+30,'.'+p['pin']+' →',20,MUTED)
    return h

y=s.section(overview_h+20,'02','全部生产模块端子接线图 + 仿真边界','每一个实例端口均从源码提取并与 mixed VCD 核对。输入向右进入硬件，输出向右离开硬件；同N编号相连。')
for i in range(0,len(instances),3):
    hs=[terminal_card(a,60+j*1560,y) for j,a in enumerate(instances[i:i+3])]
    y+=max(hs)+28

y=s.section(y+10,'03','全部顶层组合硬件接线','下列逻辑真实存在于 cpu_datapath / cpu_control 顶层：加法器、比较器、MUX、字段抽取、复位限定与使能逻辑。')
def combo_card(item,x,y,w=1510):
    color=GREEN if item['scope']=='C' else BLUE
    ins=[p for p in item['ports'] if p['direction']=='input']; outs=[p for p in item['ports'] if p['direction']=='output']
    input_lines=[]; output_lines=[]
    for p in ins: input_lines.append(f"{netids[p['key']]} {p['net']} [{p['width']}]")
    for p in outs: output_lines.append(f"{netids[p['key']]} {p['net']} [{p['width']}]")
    formula=textwrap.wrap(item['formula'],85,break_long_words=True)
    h=140+max(len(input_lines),len(output_lines),1)*36+len(formula)*29
    s.rect(x,y,w,h,'#fff',LINE,10); s.text(x+18,y+10,item['id'],25,color,True)
    s.text(x+18,y+51,'输入网络',21,MUTED); s.text(x+920,y+51,'输出网络',21,MUTED)
    for i,label in enumerate(input_lines): s.text(x+18,y+84+i*36,label,22)
    for i,label in enumerate(output_lines): s.text(x+920,y+84+i*36,label,22)
    ry=y+88+max(len(input_lines),len(output_lines),1)*36
    s.rect(x+680,y+83,170,max(len(input_lines),len(output_lines),1)*36,color,None,10)
    s.text(x+701,y+94,'组合逻辑',22,'#fff')
    s.line([(x+625,y+110),(x+680,y+110)],color,3,True)
    s.line([(x+850,y+110),(x+908,y+110)],color,3,True)
    for i,label in enumerate(formula): s.text(x+18,ry+12+i*29,label,21,MUTED)
    return h
for i in range(0,len(combos),3):
    hs=[combo_card(a,60+j*1560,y) for j,a in enumerate(combos[i:i+3])]; y+=max(hs)+25

y=s.section(y+10,'04','全部顶层网络：驱动端 → 连线 → 所有接收端','G=Control/Datapath接口或存储器外部接口；D=Datapath内部；C=Control内部。未消费输出也明确列出，防止把诊断线画成控制线。')
ledger=[]
for k in sorted(netinfo):
    label=f"{netids[k]}  {k}  [{netinfo[k]['width']} bit]"
    src='驱动：'+drivers[k][0]
    dest='接收：'+('; '.join(sinks[k]) if sinks[k] else '未消费（诊断/保留输出）')
    rows=[label]+textwrap.wrap(src,85)+textwrap.wrap(dest,85)
    ledger.append((k,rows))
cols=[[],[],[]]; heights=[0,0,0]
for k,rows in ledger:
    col=min(range(3),key=lambda c:heights[c]); cols[col].append((k,rows)); heights[col]+=len(rows)*30+35
for col,items in enumerate(cols):
    yy=y; x=65+1560*col
    for k,rows in items:
        color=GREEN if k.startswith('C.') else BLUE
        s.text(x,yy,rows[0],25,color,True)
        for i,t in enumerate(rows[1:]): s.text(x+25,yy+35+i*30,t,21,INK)
        hh=len(rows)*30+35; s.line([(x,yy+hh-12),(x+1500,yy+hh-12)],LINE,1)
        yy+=hh
y+=max(heights)

y=s.section(y+10,'05','模块内部波形节点与已实现状态','端口线已在02完整画出；此处补齐子模块内部硬件节点。寄存器堆数组虽未被VCD展开，仍列为已实现硬件。')
for i in range(0,len(internal),3):
    hs=[]
    for j,(inst,rows) in enumerate(internal[i:i+3]):
        wiring=internal_wiring(inst,rows)
        x=60+j*1560; h=135+len(rows)*40+len(wiring)*34; hs.append(h)
        s.rect(x,y,1510,h,'#fff',LINE,10); s.text(x+18,y+12,inst['id'],27,GREEN if inst['scope']=='C' else BLUE,True)
        for r,(name,width) in enumerate(rows):
            yy=y+65+r*40; s.text(x+18,yy,name,23); s.text(x+620,yy,width,23,MUTED)
            s.line([(x+570,yy+17),(x+606,yy+17)],BLUE,2,True)
        wy=y+90+len(rows)*40
        for r,label in enumerate(wiring): s.text(x+18,wy+r*34,label,21,MUTED)
    y+=max(hs)+25

y=s.section(y+10,'06','位宽、层级与验证边界','这是一张基于已存在仿真证据的硬件接线文档；本次绘图未重新运行仿真，也未修改生产 RTL。')
notes=[
    'decode_t = 28 bit：alu4 + src_a2 + src_b2 + regwrite1 + memread1 + memwrite1 + load_type3 + store_type2 + wb2 + branch3 + jump2 + imm3 + use1 + use2。',
    'IF/ID有效载荷97 bit；ID/EX有效载荷204 bit；EX/MEM有效载荷112 bit；MEM/WB有效载荷105 bit（按寄存器输出字段求和，均不含clk/rst/flush）。',
    'fetch_adapter 状态：req_valid_q1 + req_pc_q32 + req_pc4_q32 + buffer_valid_q1 + buffer_instr_q32 + buffer_pc_q32 + buffer_pc4_q32 = 162 bit。',
    'regfile：regs[0:31]，每项32 bit；x0读为0且禁止写入。WB→ID旁路已在组合读取逻辑实现；VCD未展开数组，不等于寄存器堆未实现。',
    'address_decoder内部 sram_offset / mmio_offset 为33 bit，避免地址范围溢出；LSU内部 selected_byte8 / selected_half16。',
    'mmio_ready是零等待合同条件；当前硬件没有可变等待的MMIO暂停状态机。MMIO默认基址0x40000000，SRAM默认0x00000000，参数仍需共同冻结。',
    '存储器模型与CNN MMIO stub仅作为已观测波形的边界；不代表实体SRAM/CNN/FPGA验证通过。未实现模块不画成已实现硬件。',
    '05补齐内部节点的数据依赖箭头与选择条件；模块内位操作/译码真值表由对应RTL定义。ALU实现ADD/SUB/AND/OR/XOR/SLT/SLTU/SLL/SRL/SRA。',
    '波形中的参数、testbench计数器、函数局部量和for循环integer不属于硬件连线；均从本图排除。assert/$warning为仿真检查，也不画成生产硬件。',
    '完整来源、逐端口位宽、连线驱动/扇出与覆盖核对保存在同目录 hardware_audit.json；N编号在整张图内唯一。',
]
for i,t in enumerate(notes): s.text(80,y+i*48,t,24,MUTED)
height=y+len(notes)*48+55

audit=dict(zip=str(ZIP),zip_sha256=hashlib.sha256(ZIP.read_bytes()).hexdigest(),archive_verified_sources=zip_checks,
    waveform=str(RUN/'mixed/waves/real_control_datapath.vcd'),waveform_sha256=hashlib.sha256((RUN/'mixed/waves/real_control_datapath.vcd').read_bytes()).hexdigest(),
    waveform_declarations_validated=validated,instances=instances,combinational_blocks=combos,
    networks={k:dict(id=netids[k],**d,drivers=drivers[k],sinks=sinks[k]) for k,d in netinfo.items()},
    internal_nodes=[dict(instance=i['id'],nodes=r) for i,r in internal],
    production_sources={str(v['path']):hashlib.sha256(v['path'].read_bytes()).hexdigest() for v in modules.values() if 'models' not in str(v['path'])},
    full_image_size=[W,height],excluded_production_wave_nodes=excluded_wave_nodes,
    production_wave_nodes_covered=len(production_wave_nodes)-len(excluded_wave_nodes))
(OUT/'hardware_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(networks=len(netinfo),instances=len(instances)-3,combos=len(combos),validated=len(validated),size=[W,height]),ensure_ascii=False),flush=True)
full=s.save(OUT/'control_datapath_all_hardware',height)
overview=Sheet(); overview.ops=overview_ops
overview.save(OUT/'control_datapath_overview',overview_h)
full.thumbnail((1200,10000)); full.save(OUT/'control_datapath_full_preview.png')
print(str(OUT),flush=True)
