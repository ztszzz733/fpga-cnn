@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0assemble_and_open_mover23_top_waveform.ps1"
if errorlevel 1 (
  echo.
  echo Waveform package could not be opened. Check the message above.
  pause
)
