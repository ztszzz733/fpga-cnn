@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0dual\control.vcd" -a "%~dp0dual_mac.gtkw" -S "%~dp0dual_mac.tcl"
