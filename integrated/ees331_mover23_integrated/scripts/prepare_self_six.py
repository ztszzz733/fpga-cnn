"""Verify and report a completed six-image full RTL run, preserving old reports."""
import hashlib
import json
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def local(p):
    s=str(p)
    return Path('D:/'+s[len('/mnt/d/'):]) if s.startswith('/mnt/d/') else Path(s)
def main(run):
    run=local(run);r=json.loads((run/'result.json').read_text())
    assert r['status']=='PASS' and r['full_network'] and r['frames']==6
    for name,digest in r['source_signature']['sources'].items(): assert sha(ROOT/name)==digest,name
    data=local(r['data']);m=json.loads((data/'manifest.json').read_text())
    assert sha(data/'manifest.json')==r['manifest_sha256']
    for name,digest in m['files_sha256'].items(): assert sha(data/name)==digest,name
    assert m['total_tasks']==786 and m['input_shape']==[112,112,3] and m['final_bytes_per_frame']==128
    metric=r['scenarios']['overlap']['metrics'];src=run/'overlap'
    output=(src/'outputs.bin').read_bytes();assert len(output)==768 and sha(src/'outputs.bin')==m['final_expected_sha256']
    expected=(data/'expected.bin').read_bytes()
    for f,j in enumerate(j for j in m['jobs'] if j['result']):
        assert output[f*128:(f+1)*128]==expected[j['expected_offset']:j['expected_offset']+j['bytes']]
    assert metric['commands']==786 and metric['results']==6 and metric['macs']==m['total_macs']
    assert metric['multi_frame_work_cycles']>0 and metric['cross_operator_work_cycles']>0
    out=ROOT/'deliverables'/('self_cnn_six_'+run.name);out.mkdir(exist_ok=True)
    for name in ['outputs.bin','events.csv','metrics.json','mac_detail.vcd','pipeline_detail.vcd']:
        shutil.copyfile(src/name,out/name)
    shutil.copyfile(run/'result.json',out/'result.json')
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    im=Image.new('RGB',(1500,620),'#101820');d=ImageDraw.Draw(im)
    d.text((25,18),'六张完整 MobileFaceNet — 真实 RTL 帧时序（100MHz条件换算）',font=font,fill='white')
    colors=['#63bbef','#ffbb66','#a4d977','#e88fb3','#a6a4ff','#58d7c5']
    scale=1180/metric['cycles']
    for i,f in enumerate(metric['frames']):
        y=85+i*72;d.text((20,y),str(f['frame']),font=font,fill=colors[i])
        for a,b,dy,color in [(f['input_begin'],f['input_commit'],0,'#777777'),(f['first_launch'],f['read_complete'],23,colors[i])]:
            d.rectangle((140+a*scale,y+dy,140+b*scale,y+dy+16),fill=color)
    d.text((25,535),'灰：输入传输；彩：首次任务发射至结果读完（含等待，不代表每拍计算）',font=font,fill='white')
    d.text((25,575),f"横轴 0 → {metric['cycles']/100000:.5f} ms；实际工作重叠 {metric['multi_frame_work_cycles']} 拍",font=font,fill='white')
    im.save(out/'frame_timeline.png')
    for wave in ['mac_detail','pipeline_detail']:
        names=[]
        for line in (out/(wave+'.vcd')).read_text().splitlines():
            if line.startswith('$var '): names.append('cnn_full.'+line.split()[4]+(f'[{int(line.split()[2])-1}:0]' if int(line.split()[2])>1 else ''))
        assert len(names)==len(set(names))==10
        (out/(wave+'.gtkw')).write_text('[dumpfile] "'+(out/(wave+'.vcd')).as_posix()+'"\n'+'\n'.join('@22\n'+name if '[' in name else '@28\n'+name for name in names)+'\n')
        (out/('verify_'+wave+'.tcl')).write_text('set log [open validation_'+wave+'.log w]\nset failure [catch {\nset shown [gtkwave::getDisplayedSignals]\nputs $log "SIGNALS=[llength $shown] UNIQUE=[llength [lsort -unique $shown]]"\nif {[llength $shown] != 10 || [llength [lsort -unique $shown]] != 10} {error "missing/duplicate signals"}\nputs $log "PASS"\n} message]\nif {$failure} {puts $log "FAIL $message"}\nclose $log\ngtkwave::/File/Quit\n')
    report=f'''# 六张完整图片 MobileFaceNet 仿真

本次完整 RTL PASS：786任务，6份128字节输出，MAC总数 {metric['macs']:,}，输出逐字节匹配独立整数参考。

当前配置 K3×2、K1×4，DW7/Post/Add/Pad各1；六帧同批次交错处理，不是4+2分批。

- 编译：{r['compile_seconds']:.3f} 秒（本次复用小数据门槛程序）。首次编译时间见小回归记录。
- 本次电脑执行：{r['wall_seconds']:.3f} 秒；硬件周期 {metric['cycles']:,}。
- 假设100MHz硬件时间：{metric['cycles']/100000:.5f} ms，不代表已验证板级频率。
- 跨图实际工作重叠：{metric['multi_frame_work_cycles']:,} 拍；跨类工作重叠：{metric['cross_operator_work_cycles']:,} 拍。
- 输出SHA256：`{sha(src/'outputs.bin')}`。

输入为6张不同合成112×112 RGB数值测试图，完整预训练MobileFaceNet运算。首图诊断量化尺度固定复用，不能证明人脸识别准确率。输入由TB通过真实SRAM接口逐张写入，整张提交后该帧开始计算；不是UART、CPU固件接入或层内条带流水。

仿真SRAM为32MiB，初始化区{m['init_bytes']:,}字节；未解决512KiB生产存储适配。

`frame_timeline.png`显示真实帧时序。`mac_detail.gtkw`与`pipeline_detail.gtkw`分别观察实际MAC与跨类工作，10根唯一信号。VCD只覆盖256拍局部窗口，横轴起点为窗口相对零点，不是全网启动时间；全程事件见events.csv。unit_active含等待，operator_work表示有效运算/推进；mem_valid/ready/write/response表示各实例存储握手；frames_ready为六帧输入就绪位；result_valid/ready为结果发布/读完确认；completed_count为任务完成数。

运行目录：`{run}`。保留原四图交付不覆盖。GTKWave实际载入校验记录另行保存；生成会话本身不等于已经GUI验证。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    (out/'provenance.json').write_text(json.dumps(dict(run=str(run),result_sha256=sha(run/'result.json'),reporter_sha256=sha(Path(__file__)),files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='provenance.json'}),indent=2))
    print(out)
if __name__=='__main__': main(sys.argv[1])
