@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0handoff.vcd" -a "%~dp0first_ack.gtkw" -S "%~dp0first_ack.tcl"
