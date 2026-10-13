@echo off
cd /d "%~dp0"
"..\..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" "control.vcd" "control.gtkw"
