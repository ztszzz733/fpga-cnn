@echo off
cd /d "%~dp0"
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0first_two.fst" -a "%~dp0first_two.gtkw" -S "%~dp0show_first_two.tcl"
