@echo off
cd /d "%~dp0"
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0first_two.fst" -a "%~dp0frame_2_write.gtkw" -S "%~dp0show_frame_2_write.tcl"
