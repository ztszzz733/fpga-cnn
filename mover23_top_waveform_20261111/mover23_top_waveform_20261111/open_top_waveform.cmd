@echo off
setlocal
set "WAVE_DIR=%~dp0"
set "GTK_BIN=%WAVE_DIR%runtime\gtkwave64\bin"
if not exist "%GTK_BIN%\gtkwave.exe" set "GTK_BIN=%WAVE_DIR%..\..\tools\gtkwave\portable\gtkwave64\bin"
if not exist "%WAVE_DIR%mover23_top_raw.vcd" (
  echo Missing original VCD: %WAVE_DIR%mover23_top_raw.vcd
  pause
  exit /b 1
)
if not exist "%GTK_BIN%\gtkwave.exe" (
  echo Missing GTKWave executable: %GTK_BIN%\gtkwave.exe
  pause
  exit /b 1
)
set "PATH=%GTK_BIN%;%SystemRoot%\System32;%SystemRoot%"
start "" /D "%WAVE_DIR%" "%GTK_BIN%\gtkwave.exe" -g -f "%WAVE_DIR%mover23_top_raw.vcd" -a "%WAVE_DIR%top_interconnect.gtkw" -S "%WAVE_DIR%top_milestones.tcl"
