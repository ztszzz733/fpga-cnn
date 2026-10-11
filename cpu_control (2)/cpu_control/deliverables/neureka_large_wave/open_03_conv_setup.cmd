@echo off
setlocal
set "GTK=%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe"
start "" "%GTK%" -f "%~dp0controls.vcd" -a "%~dp003_conv_setup.gtkw" -S "%~dp003_conv_setup.tcl"
