@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0soc_top.fst" -a "%~dp0all_modules.gtkw"
