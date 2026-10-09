@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Please extract the whole ZIP to a local folder first.
  pause
  exit /b 1
)
if not exist "runtime\gtkwave64\bin\gtkwave.exe" goto missing
if not exist "waves\soc_wires.vcd" goto missing
if /i "%~1"=="--self-check" (
  start "" /wait "runtime\gtkwave64\bin\gtkwave.exe" -f "waves\soc_wires.vcd" -a "waves\soc_cnn_detail.gtkw" -r "waves\soc_view.rc" -S "verification\verify_portable.tcl"
) else (
  start "" "runtime\gtkwave64\bin\gtkwave.exe" -f "waves\soc_wires.vcd" -a "waves\soc_cnn_detail.gtkw" -r "waves\soc_view.rc"
)
popd
exit /b 0
:missing
echo Required bundled files are missing. Extract the whole ZIP, not only this CMD.
pause
popd
exit /b 1
