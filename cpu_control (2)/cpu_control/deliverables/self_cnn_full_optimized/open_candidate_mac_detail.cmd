@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" -f "%~dp0evidence\candidate\mac_detail.vcd" -a "%~dp0candidate_mac_detail.gtkw" -S "%~dp0candidate_mac_detail.tcl"
