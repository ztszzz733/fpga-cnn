@echo off
setlocal
set "GTK_BIN=D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin"
set "PATH=%GTK_BIN%;%SystemRoot%\System32;%SystemRoot%"
start "" /D "%~dp0" "%GTK_BIN%\gtkwave.exe" -g -f "%~dp0full_start_states.fst" -a "%~dp0full_start_states.gtkw"
