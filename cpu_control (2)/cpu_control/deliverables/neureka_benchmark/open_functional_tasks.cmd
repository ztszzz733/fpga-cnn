@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
start "" "%GTK%" -f "%~dp0functional_tasks.vcd" -a "%~dp0functional_tasks.gtkw" -S "%~dp0functional_view.tcl"
