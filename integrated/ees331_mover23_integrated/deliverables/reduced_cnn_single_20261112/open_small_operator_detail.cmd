@echo off
cd /d "%~dp0"
start "" "D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" "small_states.fst" "small_operator_detail.gtkw"
