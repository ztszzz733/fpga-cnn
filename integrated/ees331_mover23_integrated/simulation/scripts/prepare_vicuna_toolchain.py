"""Native, one-pass extraction of just the tools needed by the RVV smoke tests."""
from pathlib import Path, PurePosixPath
import hashlib, json, re, shutil, tarfile, time
from run_vicuna_small import ROOT, STAGE

def main():
    start=time.monotonic()
    exe=STAGE/'model/verilated_model'
    previous=json.loads((ROOT/'build/runs/20261012_180952_vicuna_small/result.json').read_text())
    assert hashlib.sha256(exe.read_bytes()).hexdigest()==previous['simulator_sha256']
    print('Compiled model hash verified',flush=True)
    archive=ROOT/'.tools/downloads/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz'
    expected=Path(str(archive)+'.sha').read_text().split()[0]
    digest=hashlib.sha256()
    with archive.open('rb') as f:
        for data in iter(lambda:f.read(4*1024*1024),b''): digest.update(data)
    assert digest.hexdigest()==expected
    print('Archive hash verified',flush=True)
    dest=STAGE/'toolchain'; dest.mkdir(exist_ok=True)
    root=dest.resolve(); links=[]; manifest={}; count=0; last=time.monotonic()
    with tarfile.open(archive,mode='r|gz',bufsize=1024*1024) as tf:
        for member in tf:
            rel=PurePosixPath(member.name)
            base=rel.name
            wanted=bool(re.fullmatch(r'riscv-none-elf-(gcc(?:-[\d.]+)?|as|ld(?:\.bfd)?|objcopy)',base))
            wanted |= base in {'cc1','collect2','specs'} or '.so' in base
            wanted |= rel.parts[1:3]==('riscv-none-elf','bin') and base in {'as','ld','ld.bfd'}
            if not wanted or member.isdir(): continue
            assert not rel.is_absolute() and '..' not in rel.parts
            target=dest.joinpath(*rel.parts)
            assert target.resolve().is_relative_to(root)
            target.parent.mkdir(parents=True,exist_ok=True)
            if member.issym() or member.islnk():
                link=(target.parent/member.linkname).resolve() if member.issym() else (dest/member.linkname).resolve()
                assert link.is_relative_to(root)
                links.append((target,link)); continue
            assert member.isfile(),member.name
            with tf.extractfile(member) as src, target.open('wb') as dst:
                shutil.copyfileobj(src,dst,1024*1024)
            manifest[member.name]=member.size; count+=1
            if time.monotonic()-last>15:
                print(f'Extracted {count} required files; {time.monotonic()-start:.1f}s',flush=True); last=time.monotonic()
    # Materialize links as copies for Windows compatibility; never seek back
    # through the compressed archive to resolve them.
    while links:
        remaining=[]
        for target,link in links:
            if link.is_file(): shutil.copyfile(link,target)
            else: remaining.append((target,link))
        assert len(remaining)<len(links),'unresolved toolchain links'
        links=remaining
    gcc=dest/'xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc'
    assert gcc.exists()
    (dest/'minimal_manifest.json').write_text(json.dumps(manifest,indent=2))
    (dest/'ready.sha256').write_text(expected+'\n')
    print(f'READY: {count} files, {time.monotonic()-start:.2f} seconds',flush=True)

if __name__=='__main__': main()
