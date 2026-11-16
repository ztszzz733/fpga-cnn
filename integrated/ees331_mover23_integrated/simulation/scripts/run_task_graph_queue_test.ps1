$ErrorActionPreference='Stop'
$root=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$build=Join-Path $root 'simulation/build/task_graph_queue_test'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$path={param($p) ([System.IO.Path]::GetFullPath($p)).Replace('\','/')}
$rtl=& $path (Join-Path $root 'rtl/cnn_ddr/storage_plan_queue.sv')
$tb=& $path (Join-Path $root 'simulation/tb/integration/task_storage_queue_tb.sv')
$obj=& $path $build
$env:VERILATOR_ROOT='C:/msys64/ucrt64/share/verilator'
& 'C:/msys64/ucrt64/bin/verilator_bin.exe' --cc --timing --main --top-module task_storage_queue_tb -Wno-fatal -Wno-TIMESCALEMOD --Mdir $obj $rtl $tb *> (Join-Path $build 'verilator.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $build 'verilator.log') -Tail 30;throw 'Verilator failed'}
$cpp=@(Get-ChildItem -LiteralPath $build -Filter '*.cpp' | ForEach-Object {& $path $_.FullName})
$cpp+=@('C:/msys64/ucrt64/share/verilator/include/verilated.cpp','C:/msys64/ucrt64/share/verilator/include/verilated_threads.cpp','C:/msys64/ucrt64/share/verilator/include/verilated_timing.cpp')
$exe=& $path (Join-Path $build 'Vtask_storage_queue_tb.exe')
& 'C:/msys64/ucrt64/bin/g++.exe' -std=c++20 -O1 -w -DVL_TIME_CONTEXT '-IC:/msys64/ucrt64/share/verilator/include' '-IC:/msys64/ucrt64/share/verilator/include/vltstd' "-I$obj" $cpp -o $exe *> (Join-Path $build 'gpp.log')
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath (Join-Path $build 'gpp.log') -Tail 30;throw 'g++ failed'}
& $exe *> (Join-Path $build 'simulation.log')
$code=$LASTEXITCODE
Get-Content -LiteralPath (Join-Path $build 'simulation.log') -Tail 12
if($code -ne 0){throw 'Plan queue test failed'}
