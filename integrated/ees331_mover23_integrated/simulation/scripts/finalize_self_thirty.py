"""Seal the thirty-frame report after visual review and actual GTKWave loading."""
import argparse
from html.parser import HTMLParser
import subprocess
from pathlib import Path
from prepare_self_ten import ROOT, read, save, sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('directory',type=Path);ap.add_argument('--png-reviewed',action='store_true')
    args=ap.parse_args();assert args.png_reviewed,'Visually inspect all eight PNGs first'
    out=args.directory.resolve();text=(out/'task_timeline/index.html').read_text(encoding='utf-8')
    class Options(HTMLParser):
        def __init__(self):super().__init__();self.selected=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='option' and 'selected' in a:self.selected.append(a['value'])
    p=Options();p.feed(text);assert p.selected==['full'] and 'f<130' in text and '__TASK_DATA__' not in text
    js=ROOT/'build/self_thirty_timeline_check.js';js.write_text(text.split('<script>')[1].split('</script>')[0],encoding='utf-8')
    subprocess.run(['C:/Users/windows/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe','--check',str(js)],check=True)
    rows=read(out/'task_timeline/tasks.json');assert len(rows)==3960 and len({r['frame'] for r in rows})==30
    assert read(out/'gtkwave_validation.json')['status']=='PASS'
    for name in ('mac_detail','pipeline_detail'):
        log=(out/('validation_'+name+'.log')).read_text();assert 'SIGNALS=10 UNIQUE=10' in log and 'PASS' in log
    r=read(out/'result.json');assert r['status']=='PASS' and r['frames']==30
    for name,h in r['source_signature']['sources'].items():assert sha(ROOT/name)==h,name
    save(out/'artifact_validation.json',dict(status='PASS',png_visual_review=['output_cadence','full_network','images_1_10','images_11_20','images_21_30','cross_operator','mac_detail','pipeline_detail'],
        javascript_syntax='PASS',default_range='full',task_rows=3960,frames=30,gtkwave_actual_load='PASS',
        browser_preview='Not performed: browser tool blocks local file protocol; no workaround attempted'))
    p=out/'README.md';s=p.read_text(encoding='utf-8')
    note='\n交付检查：八张PNG已视检，GTKWave实际加载两会话各10根唯一信号PASS。交互图30行、3960条记录、默认全程和JavaScript语法静态检查通过；file协议受工具限制，未做浏览器预览，也未绕过。\n'
    if note not in s:p.write_text(s+note,encoding='utf-8')
    provenance=read(out/'provenance.json')
    provenance['report_scripts_sha256']={name:sha(ROOT/'scripts'/name) for name in ('prepare_self_thirty.py','prepare_self_ten.py','finalize_self_thirty.py')}
    provenance['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}
    save(out/'provenance.json',provenance);print('PASS thirty-frame artifact QA and final provenance')

if __name__=='__main__':main()
