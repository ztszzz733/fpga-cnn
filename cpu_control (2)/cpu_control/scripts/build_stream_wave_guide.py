"""Render the local wave guide using its limited Markdown vocabulary."""
from pathlib import Path
import html,re,sys

out=Path(__file__).absolute().parents[1]/'deliverables/stream_six_images'
name=sys.argv[1] if len(sys.argv)>1 else '波形阅读指南'
def inline(s):
    s=html.escape(s)
    s=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',r'<img alt="\1" src="\2">',s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)

body=[];table=False
for line in (out/(name+'.md')).read_text(encoding='utf-8').splitlines():
    if line.startswith('|'):
        if re.fullmatch(r'[|:\- ]+',line):continue
        cells=line.strip('|').split('|');tag='td' if table else 'th'
        if not table:body.append('<table>');table=True
        body.append('<tr>'+''.join(f'<{tag}>{inline(c.strip())}</{tag}>' for c in cells)+'</tr>')
        continue
    if table:body.append('</table>');table=False
    if not line:continue
    if line.startswith('#'):
        n=len(line)-len(line.lstrip('#'));body.append(f'<h{n}>{inline(line[n:].strip())}</h{n}>')
    else:body.append('<p>'+inline(line)+'</p>')
if table:body.append('</table>')
(out/(name+'.html')).write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>流式仿真波形阅读指南</title><style>body{max-width:1500px;margin:40px auto;padding:0 24px;font:18px/1.7 Microsoft YaHei,sans-serif;color:#172233;background:#f5f7fa}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:16px}td,th{padding:10px;border:1px solid #ccd4df}th{background:#e8edf4}code{color:#315c93}a{color:#1266ac}h2{margin-top:42px}</style>'''+''.join(body)+'</html>',encoding='utf-8')
print(out/(name+'.html'))
