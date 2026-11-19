from pathlib import Path
import subprocess
BASE=Path(__file__).resolve().parent
EXE=Path('D:/code/FPGA1/tools/legacy-tools/gtkwave/portable/gtkwave64/bin/gtkwave.exe')
s=subprocess.STARTUPINFO();s.dwFlags|=subprocess.STARTF_USESHOWWINDOW;s.wShowWindow=0
with (BASE/'wave_launcher.log').open('w') as log:
 p=subprocess.run([str(EXE),'-f',str(BASE/'small_control.vcd'),'-a',str(BASE/'small_control.gtkw'),'-S',str(BASE/'verify_wave.tcl')],cwd=BASE,stdout=log,stderr=subprocess.STDOUT,timeout=45,startupinfo=s,creationflags=subprocess.CREATE_NO_WINDOW)
text=(BASE/'wave_validation.log').read_text()
assert p.returncode==0 and 'PASS' in text,text
print(text)
