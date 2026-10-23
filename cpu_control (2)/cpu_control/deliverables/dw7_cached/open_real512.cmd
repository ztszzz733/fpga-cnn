@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0real512.vcd" -a "%~dp0real512.gtkw" -S "%~dp0real512.tcl"
