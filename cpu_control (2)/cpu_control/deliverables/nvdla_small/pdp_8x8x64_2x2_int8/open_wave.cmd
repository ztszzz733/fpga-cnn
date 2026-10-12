@echo off
start "" "D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0control.gtkw" -S "%~dp0view.tcl"
