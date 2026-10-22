@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp002_dual_compute.gtkw" -S "%~dp002_dual_compute.tcl"
