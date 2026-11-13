"""Seal the five-frame report after PNG review and actual GTKWave validation."""
import argparse
from html.parser import HTMLParser
import subprocess
from pathlib import Path
from prepare_self_ten import ROOT,read,save,sha

def main(expected_frames=5):
    ap=argparse.ArgumentParser();ap.add_argument('directory',type=Path);ap.add_argument('--png-reviewed',action='store_true')
    a=ap.parse_args();assert a.png_reviewed,'Review all PNGs before sealing'
    nf=expected_frames;assert nf in (5,10)
    out=a.directory.resolve();text=(out/'task_timeline/index.html').read_text(encoding='utf-8')
    class Options(HTMLParser):
        def __init__(self):super().__init__();self.selected=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='option' and 'selected' in attrs:self.selected.append(attrs['value'])
    parser=Options();parser.feed(text)
    assert parser.selected==['full'] and text.count(f'f<{100+nf}')==2 and '__TASK_DATA__' not in text
    assert 'K1#0～5是6套1×1，Post共3套' in text
    js=out/'task_timeline/syntax_check.js'
    js.write_text(text.split('<script>')[1].split('</script>')[0],encoding='utf-8')
    subprocess.run(['C:/Users/windows/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe','--check',str(js)],check=True)
    rows=read(out/'task_timeline/tasks.json')
    assert len(rows)==132*nf and {r['frame'] for r in rows}==set(range(100,100+nf))
    assert len([r for r in rows if r['node'] is not None])==131*nf
    assert read(out/'gtkwave_validation.json')['status']=='PASS'
    for name in ('mac_detail','pipeline_detail'):
        log=(out/('validation_'+name+'.log')).read_text()
        assert 'SIGNALS=10 UNIQUE=10' in log and 'PASS' in log
        variables=[line.split() for line in (out/(name+'.vcd')).read_text().splitlines() if line.startswith('$var ')]
        assert len(variables)==10 and all(int(row[2])==16 for row in variables[:6])
    result=read(out/'result.json');assert result['status']=='PASS' and result['frames']==nf
    for name,h in result['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    pngs=['output_cadence','full_network','cross_operator','mac_detail','pipeline_detail']
    if nf==10:pngs+=['images_1_5','images_6_10']
    save(out/'artifact_validation.json',dict(status='PASS',png_visual_review=pngs,
        javascript_syntax='PASS',default_range='full',task_rows=132*nf,frames=nf,operator_bus_width=16,gtkwave_actual_load='PASS',
        browser_preview='Not performed; static HTML/JavaScript validation only'))
    report=out/'README.md';note=f'\n交付检查：{len(pngs)}张PNG已视检；GTKWave两个会话实际载入各10根唯一信号通过，算子总线16位；{nf}行{132*nf}条记录、默认全程及JavaScript语法检查通过。交互页面未做浏览器预览。\n'
    body=report.read_text(encoding='utf-8')
    if note not in body:report.write_text(body+note,encoding='utf-8')
    provenance=read(out/'provenance.json')
    provenance['report_scripts_sha256']={name:sha(ROOT/'scripts'/name) for name in ('gen_self_five.py','gen_self_fifteen.py','run_self_six_wsl.py','prepare_self_five.py','prepare_self_fifteen.py','prepare_self_ten.py','prepare_self_thirty.py','finalize_self_five.py')}
    if nf==10:
        for name in ('prepare_reduced_ten.py','finalize_reduced_ten.py'):provenance['report_scripts_sha256'][name]=sha(ROOT/'scripts'/name)
    provenance['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}
    save(out/'provenance.json',provenance)
    print(f'PASS {nf}-frame artifact QA and provenance')

if __name__=='__main__':main()
