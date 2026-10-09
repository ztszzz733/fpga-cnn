@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
if not exist "%GTK%" (
  echo GTKWave portable not found. Place this folder under D:\cpu_control\deliverables.
  pause
  exit /b 1
)
start "" "%GTK%" -f "%~dp0soc_wires.vcd" -a "%~dp0soc_write_detail.gtkw" -r "%~dp0soc_view.rc"
