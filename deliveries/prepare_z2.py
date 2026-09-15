"""Create an isolated CPU handoff package; never modify source RTL or vectors."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'mobilefacenet'
STAGE = ROOT / 'deliveries' / 'Z2_20260915' / 'mobilefacenet'
ZIP = ROOT / 'deliveries' / 'MobileFaceNet_CPU_Z2_20260915.zip'

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def prepare():
    items = json.loads((SRC/'build/vectors/manifest.json').read_text())
    chain = [x for x in items if x['name'].startswith('chain_')]
    regions = []
    def region(name, start, size):
        regions.append(dict(name=name, start=start, end_inclusive=start+size-1,
                            payload_bytes=size, word_coverage_bytes=((start+size+3)//4*4)-(start//4*4)))
    first=chain[0]
    region('input',first['input_addr'],first['width']*first['height']*first['in_channels'])
    for name,addr in [('activation_A',0x10001),('activation_B',0x18001),('residual',0x24001),('final',0x28001)]:
        region(name,addr,max(math.prod(x['output_shape']) for x in chain if x['output_addr']==addr))
    conv=[x for x in chain if x['op'] in ('conv','depthwise')]
    weight_bytes=sum(x['out_channels']*(x['in_channels'] if x['op']=='conv' else 1)*x['kernel']**2 for x in conv)
    bias_bytes=sum(x['out_channels']*4 for x in conv)
    region('weights',conv[0]['weight_addr'],weight_bytes)
    region('bias',conv[0]['bias_addr'],bias_bytes)
    c=json.loads((SRC/'build/onnx_fixture/export/layer_config.json').read_text())
    wb=(SRC/'build/onnx_fixture/export/weight.bin').stat().st_size
    bb=(SRC/'build/onnx_fixture/export/bias.bin').stat().st_size
    audit=dict(date='2026-09-15',scope='existing deterministic fixtures; not a trained-model capacity guarantee',
        sources=['scripts/generate_vectors.py','build/vectors/manifest.json','build/onnx_fixture/export/layer_config.json'],
        synthetic112=dict(task_count=len(chain),regions=regions,
            fixed_region_payload_sum=sum(r['payload_bytes'] for r in regions),
            fixed_region_word_coverage_sum=sum(r['word_coverage_bytes'] for r in regions),
            required_contiguous_bytes_at_base_zero=max(r['end_inclusive']+1 for r in regions),
            recommended_ram_bytes=262144,layers=chain),
        onnx_fixture=dict(memory_map=c['memory_map'],weight_base=c['weight_base'],weight_bytes=wb,
            bias_base=c['bias_base'],bias_bytes=bb,required_contiguous_bytes_at_base_zero=c['bias_base']+bb,
            configured_simulation_ram_bytes=c['ram_bytes']))
    assert audit['synthetic112']['fixed_region_payload_sum']==48284
    assert audit['synthetic112']['fixed_region_word_coverage_sum']==48308
    assert audit['synthetic112']['required_contiguous_bytes_at_base_zero']==254688
    assert audit['onnx_fixture']['required_contiguous_bytes_at_base_zero']==5844
    dump(SRC/'docs/DZ1_memory_audit.json',audit)
    STAGE.mkdir(parents=True,exist_ok=False)
    ignore=shutil.ignore_patterns('__pycache__','*.pyc')
    for folder in ['rtl','tb','scripts','docs','examples']:
        shutil.copytree(SRC/folder,STAGE/folder,ignore=ignore)
    for name in ['README.md','requirements.txt']:
        shutil.copy2(SRC/name,STAGE/name)
    (STAGE/'build').mkdir()
    shutil.copytree(SRC/'build/vectors',STAGE/'build/vectors')
    shutil.copytree(SRC/'build/onnx_fixture',STAGE/'build/onnx_fixture',
                    ignore=shutil.ignore_patterns('*.vvp','*.vcd','__pycache__','*.pyc'))
    for path in (SRC/'build').iterdir():
        if path.is_file() and (path.suffix=='.log' or path.name=='verification.json' or path.name.endswith('rtl_features.bin')):
            shutil.copy2(path,STAGE/'build'/path.name)
    # Simulator task files must work after moving the package to another host.
    for path in (STAGE/'build/onnx_fixture').rglob('tasks.txt'):
        data=path.read_text()
        data=data.replace(SRC.as_posix()+'/', '')
        path.write_text(data,encoding='utf-8')
        assert SRC.as_posix() not in data
    (STAGE/'DELIVERY_README.md').write_text('''# CPU 联调交付包 Z2

日期：2026-09-15。仅包含新版 mobilefacenet；无旧版 RTL、工具安装包或本机 .deps。

正式回复：docs/发给CPU负责人_Z方对DZ1的正式回复_Z2.md。
容量报告：docs/DZ1_memory_audit.json。

从本目录的父目录运行：

```text
python mobilefacenet/scripts/run_tests.py accelerator_regs accelerator_mem_if top_smoke
python mobilefacenet/scripts/run_tests.py mobilefacenet --tasks mobilefacenet/build/vectors/tasks.txt
python mobilefacenet/scripts/run_tests.py mobilefacenet --tasks mobilefacenet/build/onnx_fixture/export/tasks.txt
```

Python 与 Icarus Verilog/VVP 必须可用；可通过 --iverilog / --vvp 指定路径。
以上命令使用内置测试或预生成向量。重新生成向量、执行软件参考或导出 ONNX 时，
需另安装 requirements.txt 中的依赖，再按 README 运行 verify_all.py。

rtl/files.f 内的路径以 mobilefacenet 目录为基准；集成时不要同时加入旧版 RTL。
ONNX tasks.txt 的数据路径已经改为工程内相对路径，寄存器值与向量字节未改变。
模型 metadata 保留历史来源路径用于追溯，运行预生成任务不依赖原机器路径。

build/verification.json 和 docs/verification.md 是此前完整验证记录。
build/Z2_delivery_checks.json 是本次在交付副本上执行的有限复核，不能代替完整系统验证。
DELIVERY_MANIFEST.json 记录除自身之外各文件的 SHA-256；压缩包旁提供包体 SHA-256。
本包未包含实体双口 SRAM wrapper、B 口适配器、官方 stub 或真实训练人脸模型。
''',encoding='utf-8')
    print(json.dumps({'stage':str(STAGE),'audit':audit['synthetic112']['required_contiguous_bytes_at_base_zero']}))

def finalize():
    checks=json.loads((STAGE/'build/Z2_delivery_checks.json').read_text())
    assert checks['status']=='passed'
    files={}
    for p in sorted(STAGE.rglob('*')):
        if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and p.suffix not in ('.pyc','.vvp','.vcd') and '__pycache__' not in p.parts:
            files[p.relative_to(STAGE).as_posix()]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    dump(STAGE/'DELIVERY_MANIFEST.json',dict(date='2026-09-15',file_count=len(files),files=files))
    with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(STAGE/name,'mobilefacenet/'+name)
        z.write(STAGE/'DELIVERY_MANIFEST.json','mobilefacenet/DELIVERY_MANIFEST.json')
    with zipfile.ZipFile(ZIP) as z:
        assert z.testzip() is None
        for name,meta in files.items():
            assert hashlib.sha256(z.read('mobilefacenet/'+name)).hexdigest()==meta['sha256']
        listed=(STAGE/'rtl/files.f').read_text().splitlines()
        assert all('mobilefacenet/'+n in z.namelist() for n in listed if n)
        for tasks in ['build/vectors/tasks.txt','build/onnx_fixture/export/tasks.txt']:
            for line in (STAGE/tasks).read_text().splitlines()[1:]:
                tokens=line.split()
                for idx in [0,-1]:
                    if tokens[idx]!='-':assert (STAGE/tokens[idx]).is_file(),tokens[idx]
    digest=hashlib.sha256(ZIP.read_bytes()).hexdigest()
    ZIP.with_suffix('.zip.sha256').write_text(digest+'  '+ZIP.name+'\n',encoding='ascii')
    print(json.dumps(dict(zip=str(ZIP),bytes=ZIP.stat().st_size,files=len(files)+1,sha256=digest)))

if __name__=='__main__':
    {'prepare':prepare,'finalize':finalize}[sys.argv[1]]()
