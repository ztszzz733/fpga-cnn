@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0dual\control.vcd" -a "%~dp0result_ack.gtkw" -S "%~dp0result_ack.tcl"
