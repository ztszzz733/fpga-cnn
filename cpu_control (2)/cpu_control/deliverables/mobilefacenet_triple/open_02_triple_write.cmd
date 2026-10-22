@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp002_triple_write.gtkw" -S "%~dp002_triple_write.tcl"
