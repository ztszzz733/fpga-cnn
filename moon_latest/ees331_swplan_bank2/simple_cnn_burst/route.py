import subprocess, ctypes, time, json
from pathlib import Path
base=Path(__file__).resolve().parent
out=base/'routed'
synth=json.loads((base/'synthesis/result.json').read_text())
assert synth['status']=='COMPLETE'
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in ['total_phys','free_phys','total_page','free_page','total_virtual','free_virtual','free_ext']]]
def remaining():
    m=Memory()
    m.length=ctypes.sizeof(m)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.free_page / 2**30
assert remaining()>=4
startup=subprocess.STARTUPINFO()
startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow=0
t=time.perf_counter()
with (out/'launcher.log').open('w') as log:
    p=subprocess.Popen(['D:/vivado/2025.2/Vivado/bin/vivado.bat','-mode','batch','-source',str(out/'route.tcl'),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],cwd=out,stdout=log,stderr=subprocess.STDOUT,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    while p.poll() is None:
        time.sleep(3)
        if remaining()<2:
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            p.wait()
            raise RuntimeError('Stopped at 2 GiB remaining commit')
assert p.returncode==0 and 'CNN_OOC_ROUTE_DONE' in (out/'vivado.log').read_text(errors='replace')
print('Route completed in',round(time.perf_counter()-t,1),'seconds')

