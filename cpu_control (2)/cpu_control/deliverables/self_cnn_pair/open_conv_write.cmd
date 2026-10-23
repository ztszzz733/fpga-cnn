@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0dual\control.vcd" -a "%~dp0conv_write.gtkw" -S "%~dp0conv_write.tcl"
