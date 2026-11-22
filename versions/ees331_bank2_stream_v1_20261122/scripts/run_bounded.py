import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, required=True)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--cwd', type=Path, required=True)
parser.add_argument('--idle-seconds',type=int,default=90)
parser.add_argument('--progress-file',type=Path)
parser.add_argument('command', nargs=argparse.REMAINDER)
args=parser.parse_args()
command=args.command[1:] if args.command and args.command[0]=='--' else args.command
args.log.parent.mkdir(parents=True, exist_ok=True)
env=os.environ.copy()
env['VERILATOR_ROOT']='C:/msys64/ucrt64/share/verilator'
started=time.monotonic()
def cpu_seconds(pid):
    if os.name!='nt':return 0.
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),
                  ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
                  ('flags',w.DWORD),('exe',w.WCHAR*260)]
    k=ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.OpenProcess.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE]
    k.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
    k.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
    k.GetProcessTimes.argtypes=[w.HANDLE,ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME),ctypes.POINTER(w.FILETIME)]
    snap=k.CreateToolhelp32Snapshot(2,0);entry=Entry();entry.size=ctypes.sizeof(entry);parents={}
    ok=k.Process32FirstW(snap,ctypes.byref(entry))
    while ok:
        parents[entry.pid]=entry.parent;ok=k.Process32NextW(snap,ctypes.byref(entry))
    k.CloseHandle(snap);ids={pid}
    while True:
        children={child for child,parent in parents.items() if parent in ids}
        if children<=ids:break
        ids|=children
    total=0.
    for child in ids:
        handle=k.OpenProcess(0x1000,False,child)
        if not handle:continue
        times=[w.FILETIME() for _ in range(4)]
        if k.GetProcessTimes(handle,*[ctypes.byref(x) for x in times]):
            total+=sum((x.dwHighDateTime<<32)|x.dwLowDateTime for x in times[2:])/1e7
        k.CloseHandle(handle)
    return total
with args.log.open('w', encoding='utf-8') as log:
    p=subprocess.Popen(command, cwd=args.cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    next_update=started+20
    last_evidence=started;previous_bytes=0;previous_cpu=0.
    while p.poll() is None:
        now=time.monotonic()
        if now-started>args.seconds:
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'], capture_output=True)
            print(f'TIMEOUT: stopped process tree {p.pid} after {args.seconds}s', flush=True)
            sys.exit(124)
        if now>=next_update:
            size=args.log.stat().st_size
            if args.progress_file and args.progress_file.exists():size+=args.progress_file.stat().st_size
            cpu=cpu_seconds(p.pid)
            if size!=previous_bytes or cpu>previous_cpu+.05:last_evidence=now
            previous_bytes=size;previous_cpu=cpu
            print(f'RUNNING elapsed={now-started:.0f}s log_bytes={size} tree_cpu={cpu:.1f}s',flush=True)
            if now-last_evidence>args.idle_seconds:
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
                print(f'STALLED: stopped process tree after {args.idle_seconds}s without log or CPU progress',flush=True)
                sys.exit(125)
            next_update=now+20
        time.sleep(.25)
print(f'EXIT={p.returncode} elapsed={time.monotonic()-started:.1f}s log={args.log}',flush=True)
if p.returncode:
    print('\n'.join(args.log.read_text(errors='replace').splitlines()[-25:]))
sys.exit(p.returncode)
