#!/usr/bin/env python3
"""统一入口：Icarus 优先，已有 Vivado XSim 可回退；不自动安装工具。"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, random, re, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def tools():
    local = ROOT / '.tools/ucrt64/bin'
    def find(name):
        p = local / (name + '.exe')
        return str(p) if p.exists() else shutil.which(name)
    result = {x: find(x) for x in ('iverilog', 'vvp', 'verilator')}
    candidates = [Path(os.environ.get('XILINX_VIVADO', '/not-found'))]
    if os.name == 'nt':
        candidates += list(Path('D:/vivado').glob('*/Vivado')) if Path('D:/vivado').exists() else []
    xvlog = shutil.which('xvlog')
    if xvlog:
        candidates.insert(0, Path(xvlog).parent.parent)
    for base in candidates:
        bindir = base / ('bin/unwrapped/win64.o' if os.name == 'nt' else 'bin')
        suffix = '.exe' if os.name == 'nt' else ''
        if all((bindir / (x + suffix)).exists() for x in ('xvlog','xelab','xsim')):
            result.update({x: str(bindir / (x + suffix)) for x in ('xvlog','xelab','xsim')})
            result['vivado_root'] = str(base)
            break
    return result

def tool_env(found):
    env = os.environ.copy()
    paths = [str(ROOT / '.tools/ucrt64/bin')]
    if 'vivado_root' in found:
        base = Path(found['vivado_root'])
        paths += [str(base/'lib/win64.o'), str(base/'bin/unwrapped/win64.o')]
        env.update(RDI_DATADIR=str(base/'data'), RDI_APPROOT=str(base), RDI_LIBDIR=str(base/'lib/win64.o'), RDI_BINDIR=str(base/'bin'),
                   RDI_BASEROOT=str(base.parent), XILINX_VIVADO=str(base),HDI_APPROOT=str(base),RDI_PLATFORM='win64',RDI_OPT_EXT='.o')
        tcl_candidates=[x for x in (base.parent/'tps/tcl/tcl8.6',base/'tps/tcl/tcl8.6') if (x/'init.tcl').exists()]
        if tcl_candidates and 'TCL_LIBRARY' not in env:
            env['TCL_LIBRARY']=str(tcl_candidates[0])
        java_candidates=list((base.parent/'tps/win64').glob('jre24*/bin/server'))
        for java in java_candidates:
            paths.extend([str(java),str(java.parent)])
    env['PATH'] = os.pathsep.join(paths+[env.get('PATH','')])
    return env

def execute(cmd, cwd, env, log, timeout=120):
    with log.open('a', encoding='utf-8') as f:
        f.write('\nCOMMAND '+json.dumps([str(x) for x in cmd],ensure_ascii=False)+'\n'); f.flush()
        try:
            p = subprocess.run([str(x) for x in cmd], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            f.write(f'\nTIMEOUT after {timeout}s\n')
            raise RuntimeError(f'执行超时；查看 {log}') from exc
    if p.returncode:
        raise RuntimeError(f'命令退出码 {p.returncode}；查看 {log}')

def defaults():
    text=(ROOT/'tb/config/tb_config.svh').read_text(encoding='utf-8')
    return {m[0]: m[1].strip('"') for m in re.findall(r'`define TB_(\w+)\s+("[^"]+"|\d+)',text)}

def vectors(run, seed, count, selected_names=None):
    with (ROOT/'tb/vectors/decode_cases.csv').open(encoding='utf-8',newline='') as f:
        rows=list(csv.DictReader(f))
    legal_names={r['name'] for r in rows[:37]}
    if selected_names:
        selected=set(selected_names)
        rows=[r for r in rows if r['name'].upper() in selected]
    rng=random.Random(seed)
    stimuli=[(r, int(r['instruction'],16),0) for r in rows]
    legal=[r for r in rows if r['name'] in legal_names]
    if count and not legal:
        raise ValueError('所选项目没有可随机化的合法指令；请使用 --random-cases 0')
    for _ in range(count):
        r=rng.choice(legal);mask=int(r['mask'],16)
        ins=(int(r['instruction'],16)&mask)|(rng.getrandbits(32)&(~mask&0xffffffff))
        stimuli.append((r,ins,1))
    with (run/'vectors.txt').open('w',encoding='ascii') as f, (run/'vector_index.csv').open('w',newline='',encoding='utf-8') as idx:
        w=csv.writer(idx);w.writerow(['vector_id','name','instruction','random'])
        for i,(r,ins,rnd) in enumerate(stimuli):
            f.write(f"{i} {ins:08x} {r['expected']} {r['illegal']} {rnd}\n")
            w.writerow([i,r['name'],f'{ins:08x}',rnd])
    return hashlib.sha256((run/'vectors.txt').read_bytes()).hexdigest()

def encode_r(funct7, funct3, rd=6, rs1=1, rs2=2):
    return (funct7<<25)|(rs2<<20)|(rs1<<15)|(funct3<<12)|(rd<<7)|0x33

def encode_i(opcode, funct3, immediate, rd=6, rs1=1):
    return ((immediate&0xfff)<<20)|(rs1<<15)|(funct3<<12)|(rd<<7)|opcode

def encode_s(funct3, immediate=0, rs1=0, rs2=2):
    imm=immediate&0xfff
    return ((imm>>5)<<25)|(rs2<<20)|(rs1<<15)|(funct3<<12)|((imm&0x1f)<<7)|0x23

def encode_b(funct3, rs1, rs2, offset=4):
    imm=offset&0x1fff
    return (((imm>>12)&1)<<31)|(((imm>>5)&0x3f)<<25)|(rs2<<20)|(rs1<<15)|(funct3<<12)|(((imm>>1)&0xf)<<8)|(((imm>>11)&1)<<7)|0x63

def encode_j(rd=6, offset=4):
    imm=offset&0x1fffff
    return (((imm>>20)&1)<<31)|(((imm>>1)&0x3ff)<<21)|(((imm>>11)&1)<<20)|(((imm>>12)&0xff)<<12)|(rd<<7)|0x6f

def stage_instruction(name, row):
    """生成可从测试 stub 的 PC=0 安全走完流水线的代表机器码。"""
    funct3=int(row['funct3'],16) if row['funct3'] not in ('any','exact') else 0
    funct7=int(row['funct7'],16) if row['funct7'] not in ('any','exact') else 0
    if name=='LUI': return (1<<12)|(6<<7)|0x37
    if name=='AUIPC': return (1<<12)|(6<<7)|0x17
    if name=='JAL': return encode_j()
    if name=='JALR': return encode_i(0x67,0,4,rs1=0)
    branch_regs={'BEQ':(1,1),'BNE':(1,2),'BLT':(1,2),'BGE':(2,1),'BLTU':(1,2),'BGEU':(2,1)}
    if name in branch_regs: return encode_b(funct3,*branch_regs[name])
    if name in {'LB','LH','LW','LBU','LHU'}: return encode_i(0x03,funct3,0,rs1=0)
    if name in {'SB','SH','SW'}: return encode_s(funct3)
    if name in {'SLLI','SRLI','SRAI'}: return encode_i(0x13,funct3,(funct7<<5)|2)
    if name in {'ADDI','SLTI','SLTIU','XORI','ORI','ANDI'}: return encode_i(0x13,funct3,2)
    if name in {'ADD','SUB','SLL','SLT','SLTU','XOR','SRL','SRA','OR','AND'}: return encode_r(funct7,funct3)
    return int(row['instruction'],16)

def stage_vectors(run, selected_names):
    with (ROOT/'tb/vectors/decode_cases.csv').open(encoding='utf-8',newline='') as f:
        all_rows=list(csv.DictReader(f))
    lookup={r['name'].upper():r for r in all_rows}
    path=run/'stage_vectors.txt'
    with path.open('w',encoding='ascii') as f:
        for vector_id,name in enumerate(selected_names):
            row=lookup[name]
            instruction=stage_instruction(name,row)
            f.write(f"{vector_id} {name} {instruction:08x} {row['expected']} {row['illegal']}\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    d=defaults();p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-tools',action='store_true')
    p.add_argument('--simulator',choices=['auto','icarus','xsim'],default='auto')
    p.add_argument('--test',choices=['all','decode','instruction','forward','load_use','branch','jump','reset','pipeline'],default=d['TEST_NAME'])
    p.add_argument('--instruction',action='append',metavar='NAME[,NAME...]',
                   help='选择一条或多条指令；可重复使用或用逗号分隔，例如 ADD 或 ADD,LW')
    p.add_argument('--stage',choices=['fetch','decode','execute','memory','writeback','all'],default='all',
                   help='--test instruction 的观察和检查阶段；默认 all')
    for arg,key in [('seed','SEED'),('random-cases','RANDOM_CASES'),('clk-period-ns','CLK_PERIOD_NS'),('reset-cycles','RESET_CYCLES'),('max-cycles','MAX_CYCLES')]:
        p.add_argument('--'+arg,type=int,default=int(d[key]))
    p.add_argument('--waves',action=argparse.BooleanOptionalAction,default=bool(int(d['DUMP_WAVES'])))
    p.add_argument('--plot',action='store_true');p.add_argument('--lint',action='store_true')
    p.add_argument('--verbose',action='store_true',default=bool(int(d['VERBOSE'])))
    p.add_argument('--stop-on-first-error',type=int,choices=[0,1],default=int(d['STOP_ON_FIRST_ERROR']))
    p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--out-root',type=Path,default=ROOT/'build/runs')
    p.add_argument('--plot-start-ns',type=float);p.add_argument('--plot-end-ns',type=float)
    p.add_argument('--plot-signals-file',type=Path,default=ROOT/'scripts/wave_signals.json')
    p.add_argument('--negative-case',choices=['mul_busy'],help='验证不支持输入会导致失败；正常验收不要使用')
    a=p.parse_args(argv)
    selected_names=[]
    for group in a.instruction or []:
        selected_names.extend(name.strip().upper() for name in group.split(',') if name.strip())
    selected_names=list(dict.fromkeys(selected_names))
    if a.instruction and not selected_names:
        p.error('--instruction 后至少要有一个名字')
    if selected_names and a.test not in ('all','decode','instruction'):
        p.error('--instruction 只用于 --test decode、--test instruction 或 --test all')
    if a.test=='instruction' and not selected_names:
        p.error('--test instruction 必须同时使用 --instruction 指定至少一条指令')
    if a.test!='instruction' and a.stage!='all':
        p.error('--stage 只用于 --test instruction')
    if selected_names:
        with (ROOT/'tb/vectors/decode_cases.csv').open(encoding='utf-8',newline='') as f:
            available={r['name'].upper() for r in csv.DictReader(f)}
        unknown=[name for name in selected_names if name not in available]
        if unknown:
            p.error('未知指令/样例名：'+', '.join(unknown)+'；可用名字见 tb/vectors/decode_cases.csv 的 name 列')
    if not (0<=a.seed<=2147483647 and a.random_cases>=0 and a.clk_period_ns>=2 and a.clk_period_ns%2==0 and a.reset_cycles>=2 and a.max_cycles>0 and a.timeout>0):
        p.error('seed 为 0..2147483647，random-cases>=0，时钟为 >=2 的偶数 ns，reset>=2，周期/超时>0')
    found=tools();env=tool_env(found);versions={}
    for name in ('iverilog','vvp','xvlog','verilator'):
        if found.get(name):
            try:
                flag={'iverilog':'-V','vvp':'-V','xvlog':'-version','verilator':'--version'}[name]
                proc=subprocess.run([found[name],flag],env=env,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=15)
                versions[name]=(proc.stdout+proc.stderr).strip().splitlines()[0]
            except Exception as exc: versions[name]=str(exc)
    versions['python']=sys.version.split()[0]
    try:
        import matplotlib
        versions['matplotlib']=matplotlib.__version__
    except ImportError: versions['matplotlib']='MISSING'
    if a.check_tools:
        print(json.dumps({'paths':found,'versions':versions},ensure_ascii=False,indent=2))
        if not ((found.get('iverilog') and found.get('vvp')) or found.get('xsim')):
            print('缺少模拟器：安装 Icarus 并加入 PATH，或设置 XILINX_VIVADO。详见 docs/README_TEST.md。');return 2
        return 0
    backend=a.simulator
    if backend=='auto': backend='icarus' if found.get('iverilog') and found.get('vvp') else 'xsim'
    required=['iverilog','vvp'] if backend=='icarus' else ['xvlog','xelab','xsim']
    if any(not found.get(x) for x in required):
        print('缺少工具：'+', '.join(x for x in required if not found.get(x))+'；执行 --check-tools，参见 docs/README_TEST.md。');return 2
    run=a.out_root.resolve()/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+f'_{os.getpid()}_{a.test}_seed{a.seed}')
    run.mkdir(parents=True);(run/'waves').mkdir();(run/'figures').mkdir()
    print('RUN_DIR='+str(run),flush=True)
    result={'status':'RUNNING','test':a.test,'seed':a.seed,'simulator':backend,'versions':versions,'command':[sys.executable,*sys.argv],
            'run_dir':str(run),'real_datapath':'NOT_RUN: not provided','lint':'NOT_RUN','errors':[]}
    result['instruction_filter']=selected_names
    result['stage']=a.stage if a.test=='instruction' else 'not_applicable'
    started=time.monotonic();waves=a.waves or a.plot
    random_count=a.random_cases if a.test in ('all','decode') else 0
    result['random_requested']=a.random_cases;result['random_scheduled']=random_count
    try:
        result['vectors_sha256']=vectors(run,a.seed,random_count,selected_names)
        if a.test=='instruction': result['stage_vectors_sha256']=stage_vectors(run,selected_names)
    except Exception as exc:
        result.update(status='FAIL',errors=['测试向量生成失败：'+str(exc)])
        (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(result['errors'][0]);return 1
    files=[ROOT/line for line in (ROOT/'tb/filelists/cpu_control.f').read_text().splitlines() if line.strip()]
    plus=[f'TEST_NAME={a.test}',f'STAGE_NAME={a.stage}',f'SEED={a.seed}',f'RANDOM_CASES={random_count}',f'CLK_PERIOD_NS={a.clk_period_ns}',f'RESET_CYCLES={a.reset_cycles}',f'MAX_CYCLES={a.max_cycles}',f'DUMP_WAVES={int(waves)}',f'VERBOSE={int(a.verbose)}',f'STOP_ON_FIRST_ERROR={a.stop_on_first_error}', 'VECTOR_PATH=vectors.txt','STAGE_VECTOR_PATH=stage_vectors.txt','VCD_PATH=waves/cpu_control.vcd']
    if a.negative_case: plus.append('NEGATIVE='+a.negative_case)
    try:
        if a.lint:
            if found.get('verilator'):
                execute([found['verilator'],'--lint-only','-Wall','--top-module','cpu_control',*files[:7]],run,env,run/'lint.log',a.timeout)
                result['lint']='PASS'
            else: result['lint']='NOT_RUN: Verilator not found'
        if backend=='icarus':
            execute([found['iverilog'],'-g2012','-Wall','-I',ROOT/'tb/config','-s','tb_cpu_control','-o','sim.vvp',*files],run,env,run/'compile.log',a.timeout)
            execute([found['vvp'],'sim.vvp',*['+'+x for x in plus]],run,env,run/'simulation.log',a.timeout)
        else:
            execute([found['xvlog'],'-sv','-d','XSIM','-i',ROOT/'tb/config',*files],run,env,run/'compile.log',a.timeout)
            execute([found['xelab'],'tb_cpu_control','-s','control_sim','-debug','all','-mt','2'],run,env,run/'compile.log',a.timeout)
            tcl=('open_vcd {waves/cpu_control.vcd}\nlog_vcd [get_objects -r /tb_cpu_control/*]\n' if waves else '')+'run all\n'+('close_vcd\n' if waves else '')+'quit\n'
            (run/'run.tcl').write_text(tcl,encoding='utf-8')
            options=[x for arg in plus for x in ('-testplusarg',arg)]
            execute([found['xsim'],'control_sim','-tclbatch','run.tcl','-onerror','quit',*options],run,env,run/'simulation.log',a.timeout)
        if not (run/'tb_summary.json').exists():
            logtext=(run/'simulation.log').read_text(encoding='utf-8',errors='replace')
            clues=[line for line in logtext.splitlines() if any(word in line for word in ('FAIL case_id','Fatal:','TIMEOUT','ERROR:'))]
            raise RuntimeError('仿真未生成汇总；'+(' | '.join(clues[-4:]) or '查看 simulation.log'))
        result['tb']=json.loads((run/'tb_summary.json').read_text())
        if result['tb']['failures'] or 'PASS CPU_CONTROL' not in (run/'simulation.log').read_text(encoding='utf-8',errors='replace'):
            raise RuntimeError('仿真未产生有效 PASS 汇总')
    except Exception as exc:
        result['errors'].append(str(exc))
    windows={}
    if (run/'case_windows.csv').exists():
        for line in (run/'case_windows.csv').read_text().splitlines():
            name,start,end=line.split(',');windows[name]={'start_ns':float(start),'end_ns':float(end)}
    (run/'case_windows.json').write_text(json.dumps(windows,indent=2),encoding='utf-8')
    if a.plot:
        try:
            from plot_waveforms import render
            groups={'decode':'decode','forwarding':'hazard','load_use':'pipeline','branch_flush':'pipeline'}
            instruction_window=f'instruction_{a.stage}'
            if instruction_window in windows: groups[instruction_window]=f'instruction_{a.stage}'
            selected=[x for x in groups if x in windows]
            if not selected: selected=['overview']
            fallback_group={'decode':'decode','forward':'hazard','load_use':'pipeline','branch':'pipeline',
                            'jump':'pipeline','pipeline':'pipeline','reset':'gating'}.get(a.test,'hazard')
            for name in selected:
                win=windows.get(name,{})
                render(run/'waves/cpu_control.vcd',a.plot_signals_file,run/'figures',
                       group=groups.get(name,fallback_group),start_ns=a.plot_start_ns if a.plot_start_ns is not None else win.get('start_ns'),
                       end_ns=a.plot_end_ns if a.plot_end_ns is not None else win.get('end_ns'),dpi=180,
                       name=name,title=f'{a.test} / {name} | seed={a.seed} | '+('FAILED' if result['errors'] else 'PASS'))
        except Exception as exc: result['errors'].append('绘图失败：'+str(exc))
    result['status']='FAIL' if result['errors'] else 'PASS';result['elapsed_seconds']=round(time.monotonic()-started,3)
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for err in result['errors']: print('ERROR: '+err)
    print(result['status']+' '+str(run/'result.json'))
    return int(bool(result['errors']))

if __name__=='__main__':
    raise SystemExit(main())
