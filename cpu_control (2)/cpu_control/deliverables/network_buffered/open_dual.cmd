@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0dual.vcd" -a "%~dp0dual.gtkw" -S "%~dp0dual.tcl"
