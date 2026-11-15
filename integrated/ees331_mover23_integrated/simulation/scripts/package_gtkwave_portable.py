"""Build a self-contained Windows x64 GTKWave sharing package."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'deliverables/gtkwave_soc_36'
PACKAGE=ROOT/'deliverables/GTKWave_SoC_36_Portable'
ARCHIVE=ROOT/'deliverables/GTKWave_SoC_36_Portable_Win64.zip'


def build():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/'tools/gtkwave/portable/gtkwave64',PACKAGE/'runtime/gtkwave64',dirs_exist_ok=True)
    waves=PACKAGE/'waves';waves.mkdir(exist_ok=True)
    for name in ['soc_wires.vcd','soc_view.rc','soc_write_detail.png','soc_all_36.png','soc_cnn_detail.png']:
        shutil.copy2(SOURCE/name,waves/name)
    expected=json.loads((SOURCE/'expected_signals.json').read_text())
    assert len(expected)==len(set(expected))==36
    for stem in ['soc_write_detail','soc_all_36','soc_cnn_detail']:
        content=(SOURCE/(stem+'.gtkw')).read_text()
        content=re.sub(r'^\[dumpfile\].*$', '[dumpfile] "waves/soc_wires.vcd"', content,flags=re.M)
        content=re.sub(r'^\[savefile\].*$',f'[savefile] "waves/{stem}.gtkw"',content,flags=re.M)
        assert 'D:\\cpu_control' not in content and 'D:/cpu_control' not in content
        (waves/(stem+'.gtkw')).write_text(content,encoding='ascii')
    launcher='''@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Please extract the whole ZIP to a local folder first.
  pause
  exit /b 1
)
if not exist "runtime\\gtkwave64\\bin\\gtkwave.exe" goto missing
if not exist "waves\\soc_wires.vcd" goto missing
if /i "%~1"=="--self-check" (
  start "" /wait "runtime\\gtkwave64\\bin\\gtkwave.exe" -f "waves\\soc_wires.vcd" -a "waves\\SESSION.gtkw" -r "waves\\soc_view.rc" -S "verification\\verify_portable.tcl"
) else (
  start "" "runtime\\gtkwave64\\bin\\gtkwave.exe" -f "waves\\soc_wires.vcd" -a "waves\\SESSION.gtkw" -r "waves\\soc_view.rc"
)
popd
exit /b 0
:missing
echo Required bundled files are missing. Extract the whole ZIP, not only this CMD.
pause
popd
exit /b 1
'''
    for name,session in [('open_write_detail','soc_write_detail'),('open_all_signals','soc_all_36'),('open_cnn_detail','soc_cnn_detail')]:
        (PACKAGE/(name+'.cmd')).write_text(launcher.replace('SESSION',session),encoding='ascii',newline='\r\n')
    verification=PACKAGE/'verification';verification.mkdir(exist_ok=True)
    expected_tcl=' '.join('{soc_wires.'+n+'}' for n in expected)
    tcl='''set folder [file dirname [file normalize [info script]]]
set log [open [file join $folder gtk_selfcheck.log] w]
set status [catch {
    set names [gtkwave::getDisplayedSignals]
    set normalized [list]
    foreach name $names {lappend normalized [regsub {\[[0-9]+:[0-9]+\]$} $name {}]}
    set expected [list EXPECTED]
    if {$normalized ne $expected} {error "Signal list/order mismatch"}
    puts $log "COUNT=[llength $names]"
    puts $log "DUMP=[gtkwave::getDumpFileName]"
    puts $log "VIEW_START=[gtkwave::getWindowStartTime]"
    foreach {t value write} {313280000 00000005 0 313300000 A5A505A5 1} {
        gtkwave::setMarker $t
        set actual [gtkwave::getTraceValueAtMarkerFromName {soc_wires.mem_wdata[31:0]}]
        set enabled [gtkwave::getTraceValueAtMarkerFromName soc_wires.mem_write]
        if {$actual ne $value || $enabled ne $write} {error "Unexpected waveform value at $t: $actual / $enabled"}
        puts $log "SAMPLE=$t $actual $enabled"
    }
    puts $log "PASS portable GTKWave loaded 36 ordered signals and verified real waveform values"
} message]
if {$status} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
'''.replace('EXPECTED',expected_tcl)
    (verification/'verify_portable.tcl').write_text(tcl,encoding='ascii')
    (PACKAGE/'README_先看这里.txt').write_text('''GTKWave 波形免安装包（Windows 64 位）

1. 先把整个 ZIP 解压到一个文件夹。不要在压缩软件内部直接运行。
2. 双击最外层的 open_write_detail.cmd。
3. GTKWave 会自动打开，包含与前一张合并图相同的全部 36 根信号，
   默认放大到 CNN 四次输出写回这一段。

无需安装 GTKWave，无需管理员权限、Python、Vivado或联网下载。
GTKWave 程序、DLL 和库文件已一起放在 runtime 文件夹中。
请保留完整文件夹结构，不要只把 CMD 或 GTKW 单独拿走。

另外两个入口：
  open_all_signals.cmd  上电至计算结束的全程视图，仍含全部 36 根信号。
  open_cnn_detail.cmd   CNN 计算至 CPU 读回的放大视图，仍含全部 36 根信号。

波形数据在 waves/soc_wires.vcd，会话配置在 waves/*.gtkw。
waves/*.png 是已由 GTKWave 实际导出的截图，也可直接用图片查看器打开。
本包适用于 Windows x64，不是 macOS/Linux 应用包。

这仍是此前的 2×2 卷积演示，结果为 [5,-1,9,11]。
未改动 RTL，也没有把它冒充“外部只送图像”的后续实现。

工具：GTKWave 3.3.100 官方 Windows 便携版（并非声称是最新版）。
来源与版本说明见 THIRD_PARTY.txt。
可选自检：在本文件夹执行 open_write_detail.cmd --self-check；
结果保存在 verification/gtk_selfcheck.log。
''',encoding='utf-8-sig')
    (PACKAGE/'THIRD_PARTY.txt').write_text('''GTKWave 3.3.100 Windows x64 official portable distribution.
The complete supplied runtime directory is included without modifying its binaries.
GTKWave copyright: (c) 1999-2019 BSI (as displayed by this release).
GTKWave and its included third-party libraries retain their respective licenses.

Upstream binary package:
https://sourceforge.net/projects/gtkwave/files/gtkwave-3.3.100-bin-win64/gtkwave-3.3.100-bin-win64.zip/download
Upstream ZIP SHA256:
cace98e9c1e5bb6ab74ac2c4c1a2913617b6db7071418d052d2cf999a1acf39d

Project and source distribution:
https://gtkwave.sourceforge.net/
https://sourceforge.net/projects/gtkwave/files/

Wave data and launch scripts are provided by the CPU_CONTROL project.
''',encoding='ascii')
    manifest={p.relative_to(PACKAGE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p.name not in ('manifest.json','gtk_selfcheck.log')}
    (PACKAGE/'manifest.json').write_text(json.dumps({'platform':'Windows x64','signals':expected,'sha256':manifest},indent=2),encoding='ascii')
    with zipfile.ZipFile(ARCHIVE,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(PACKAGE.rglob('*')):
            if p.is_file():z.write(p,'GTKWave_SoC_36/'+p.relative_to(PACKAGE).as_posix())
    with zipfile.ZipFile(ARCHIVE) as z:assert z.testzip() is None
    # Test the actual ZIP after extraction under a Chinese path with spaces.
    run=ROOT/'build/runs'/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_portable_gtkwave_check')
    relocated=run/'接收方 解压测试'
    with zipfile.ZipFile(ARCHIVE) as z:z.extractall(relocated)
    (ROOT/'deliverables/gtkwave_portable_check_location.json').write_text(json.dumps({'directory':str(relocated/'GTKWave_SoC_36'),'archive':str(ARCHIVE)},ensure_ascii=False),encoding='utf-8')
    print('ARCHIVE='+str(ARCHIVE))
    print('SIZE_MB='+str(round(ARCHIVE.stat().st_size/1024**2,2)))
    print('CHECK='+str(relocated/'GTKWave_SoC_36'))


if __name__=='__main__':build()
