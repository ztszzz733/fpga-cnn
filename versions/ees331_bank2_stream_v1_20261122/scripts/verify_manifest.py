import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
manifest=json.loads((root/'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
for item in manifest['files']:
    data=(root/item['path']).read_bytes()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
print(f"PASS {manifest['version']}: {len(manifest['files'])} published files verified")
