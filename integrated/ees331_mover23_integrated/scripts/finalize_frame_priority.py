"""Seal an inspected report after real GTKWave validation; never runs the simulation."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
import subprocess
from prepare_self_ten import ROOT, read, save, sha

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('directory',type=Path)
    ap.add_argument('--png-reviewed',action='store_true',help='Set only after visually inspecting the six PNGs')
    args=ap.parse_args();assert args.png_reviewed,'PNG visual review must be completed first'
    out=args.directory.resolve();html=(out/'task_timeline/index.html').read_text(encoding='utf-8')
    class Options(HTMLParser):
        def __init__(self):super().__init__();self.selected=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='option' and 'selected' in a:self.selected.append(a['value'])
    p=Options();p.feed(html);assert p.selected==['full']
    assert 'f<110' in html and '__TASK_DATA__' not in html
    js=ROOT/'build/frame_priority_timeline_check.js';js.write_text(html.split('<script>')[1].split('</script>')[0],encoding='utf-8')
    subprocess.run(['C:/Users/windows/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe','--check',str(js)],check=True)
    rows=read(out/'task_timeline/tasks.json');assert len(rows)==1320 and len({r['frame'] for r in rows})==10
    gtk=read(out/'gtkwave_validation.json');assert gtk['status']=='PASS'
    for name in ('mac_detail','pipeline_detail'):
        log=(out/('validation_'+name+'.log')).read_text()
        assert 'SIGNALS=10 UNIQUE=10' in log and 'PASS' in log
    comparison=read(out/'scheduling_comparison.json');assert comparison['status']=='PASS' and comparison['same_outputs']
    report=read(out/'result.json');assert report['status']=='PASS' and report['frame_priority']
    for name,digest in report['source_signature']['sources'].items():assert sha(ROOT/name)==digest,name
    save(out/'artifact_validation.json',dict(status='PASS',png_visual_review=['output_cadence','full_network','early_tasks','cross_operator','mac_detail','pipeline_detail'],
        javascript_syntax='PASS',default_range='full',task_rows=1320,frames=10,gtkwave_actual_load='PASS',
        browser_preview='Not performed: browser tool blocks local file protocol; no workaround attempted'))
    note='\n交付检查：六张PNG已视检；GTKWave实际载入两个会话，各10根唯一信号PASS。交互页JavaScript语法、十行数据及默认全程设置通过静态检查。浏览器工具限制本地file协议，未做浏览器内预览。详见artifact_validation.json。\n'
    for name in ('README.md','SCHEDULING.md'):
        p=out/name;s=p.read_text(encoding='utf-8')
        if note not in s:p.write_text(s+note,encoding='utf-8')
    provenance=read(out/'provenance.json')
    provenance['report_scripts_sha256']={name:sha(ROOT/'scripts'/name) for name in ('prepare_self_ten.py','prepare_frame_priority.py','finalize_frame_priority.py')}
    provenance['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}
    save(out/'provenance.json',provenance)
    print('PASS artifact validation and final provenance')

if __name__=='__main__':main()
