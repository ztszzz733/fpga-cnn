@echo off
setlocal
set "WAVE_DIR=%~dp0"
set "GTK_BIN=%WAVE_DIR%runtime\gtkwave64\bin"
if not exist "%GTK_BIN%\gtkwave.exe" set "GTK_BIN=%WAVE_DIR%..\..\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin"
if not exist "%GTK_BIN%\gtkwave.exe" set "GTK_BIN=%WAVE_DIR%..\..\tools\gtkwave\portable\gtkwave64\bin"
if not exist "%GTK_BIN%\gtkwave.exe" (
  echo GTKWave not found. Please select an installed GTKWave executable.
  pause
  exit /b 1
)
if not exist "%WAVE_DIR%mover23_top_raw.vcd" (
  echo Original VCD not found.
  pause
  exit /b 1
)
set "VIEW=cnn_storage_reading.gtkw"
if /I "%~1"=="all" set "VIEW=top_interconnect.gtkw"
set "PATH=%GTK_BIN%;%SystemRoot%\System32;%SystemRoot%"
start "" /D "%WAVE_DIR%" "%GTK_BIN%\gtkwave.exe" -g -f "%WAVE_DIR%mover23_top_raw.vcd" -a "%WAVE_DIR%%VIEW%" -S "%WAVE_DIR%top_milestones.tcl"
