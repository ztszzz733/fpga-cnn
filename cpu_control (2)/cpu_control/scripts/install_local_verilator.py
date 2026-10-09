"""Install a pinned Linux Verilator wheel locally without changing the system."""
import hashlib,io,json,sys,urllib.request,zipfile
from pathlib import Path

if sys.platform!='linux':
    raise SystemExit('Run this script with Python 3 inside WSL/Linux.')
root=Path(__file__).resolve().parents[1]/'.tools'
metadata=json.load(urllib.request.urlopen('https://pypi.org/pypi/verilator/5.38.0/json'))
item=next(x for x in metadata['urls'] if 'manylinux' in x['filename'] and 'x86_64' in x['filename'])
data=urllib.request.urlopen(item['url']).read()
if hashlib.sha256(data).hexdigest()!=item['digests']['sha256']:
    raise RuntimeError('PyPI SHA256 mismatch')
target=root/'verilator-linux'
zipfile.ZipFile(io.BytesIO(data)).extractall(target)
for path in target.rglob('*'):
    if path.is_file() and path.parent.name=='bin':path.chmod(0o755)
(target/'download.json').write_text(json.dumps(item,indent=2)+'\n')
print(target)
