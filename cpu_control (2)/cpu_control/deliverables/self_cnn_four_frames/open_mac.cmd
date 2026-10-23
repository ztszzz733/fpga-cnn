@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0overlap\control.vcd" -a "%~dp0mac.gtkw" -S "%~dp0mac.tcl"
