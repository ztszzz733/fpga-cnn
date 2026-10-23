@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0handoff.vcd" -a "%~dp0overview.gtkw" -S "%~dp0overview.tcl"
