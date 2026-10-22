@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0control.vcd" -a "%~dp003_layer_handoff.gtkw" -S "%~dp003_layer_handoff.tcl"
