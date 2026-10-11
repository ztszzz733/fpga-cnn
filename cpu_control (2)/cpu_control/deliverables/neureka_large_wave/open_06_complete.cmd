@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
start "" "%GTK%" -f "%~dp0controls.vcd" -a "%~dp006_complete.gtkw" -S "%~dp006_complete.tcl"
