@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0evidence\pipeline_detail.vcd" -a "%~dp0pipeline_detail.gtkw" -S "%~dp0pipeline_detail.tcl"
