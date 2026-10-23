@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0tail.gtkw" -S "%~dp0tail.tcl"
