@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0overlap16.vcd" -a "%~dp0overlap16.gtkw" -S "%~dp0overlap16.tcl"
