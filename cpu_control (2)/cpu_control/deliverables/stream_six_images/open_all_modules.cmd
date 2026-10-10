@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0all_modules.fst" -a "%~dp0all_modules.gtkw"
