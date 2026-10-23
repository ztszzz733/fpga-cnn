@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0overlap\control.vcd" -a "%~dp0result.gtkw" -S "%~dp0result.tcl"
