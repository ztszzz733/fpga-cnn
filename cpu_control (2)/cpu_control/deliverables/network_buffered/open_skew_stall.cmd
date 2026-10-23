@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0skew_stall.vcd" -a "%~dp0skew_stall.gtkw" -S "%~dp0skew_stall.tcl"
