@echo off
start "" "%~dp0..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe" "%~dp0fp32_prelu\wave.vcd" "%~dp0fp32_prelu\controls.gtkw"
