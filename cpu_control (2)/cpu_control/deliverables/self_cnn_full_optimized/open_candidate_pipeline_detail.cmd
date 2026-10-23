@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0evidence\candidate\pipeline_detail.vcd" -a "%~dp0candidate_pipeline_detail.gtkw" -S "%~dp0candidate_pipeline_detail.tcl"
