@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
start "" "%GTK%" -f "%~dp0controls.vcd" -a "%~dp005_pool_write.gtkw" -S "%~dp005_pool_write.tcl"
