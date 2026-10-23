@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp0completion.gtkw" -S "%~dp0completion.tcl"
