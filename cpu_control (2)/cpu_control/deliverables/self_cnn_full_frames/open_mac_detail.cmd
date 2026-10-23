@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0evidence\mac_detail.vcd" -a "%~dp0mac_detail.gtkw" -S "%~dp0mac_detail.tcl"
