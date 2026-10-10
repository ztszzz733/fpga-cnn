@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0power_on.fst" -a "%~dp0power_on.gtkw"
