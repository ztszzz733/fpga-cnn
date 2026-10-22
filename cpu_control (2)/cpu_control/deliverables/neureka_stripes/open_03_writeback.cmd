@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
start "" "%GTK%" -f "%~dp0control.vcd" -a "%~dp003_writeback.gtkw" -S "%~dp003_writeback.tcl"
