$ErrorActionPreference='Stop'
$root=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$build=Join-Path $root 'simulation/build/task_graph_storage_test'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$path={param($p) ([System.IO.Path]::GetFullPath($p)).Replace('\','/')}
$rtl=@(
 & $path (Join-Path $root 'rtl/cnn_ddr/cnn_plan_storage.sv')
 & $path (Join-Path $root 'rtl/cnn_ddr/storage_plan_queue.sv')
 & $path (Join-Path $root 'storage_v2/rtl/data_mover.sv')
 & $path (Join-Path $root 'storage_v2/rtl/tile_local_ram.sv')
 & $path (Join-Path $root 'storage_v2/rtl/tile_local_ram_bank4.sv')
)
$test=& $path (Join-Path $root 'simulation/tb/integration/task_plan_storage.cpp')
$stub=& $path (Join-Path $root 'simulation/tb/integration/verilated_time_stub.cpp')
$obj=& $path $build
$env:VERILATOR_ROOT='C:/msys64/ucrt64/share/verilator'
& 'C:/msys64/ucrt64/bin/verilator_bin.exe' --cc --assert --no-timing --top-module cnn_plan_storage -GCLIENTS=12 -GLOCAL_BYTES=401408 -GMOVER_TIMEOUT_CYCLES=128 -Wno-fatal --Mdir $obj -CFLAGS '-std=c++20' @rtl *> (Join-Path $build 'verilator.log')
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $build 'verilator.log') -Tail 40;throw 'Verilator failed'}
$sources=@(Get-ChildItem $build -Filter '*.cpp' | ForEach-Object {& $path $_.FullName})
$sources+=@(
 'C:/msys64/ucrt64/share/verilator/include/verilated.cpp'
 'C:/msys64/ucrt64/share/verilator/include/verilated_threads.cpp'
 $test
 $stub
)
$exe=Join-Path $build 'Vcnn_plan_storage.exe'
& 'C:/msys64/ucrt64/bin/g++.exe' -std=c++20 -O2 -w -I'C:/msys64/ucrt64/share/verilator/include' -I'C:/msys64/ucrt64/share/verilator/include/vltstd' "-I$obj" "-I$(& $path (Join-Path $root 'simulation/tb/integration'))" $sources -o (& $path $exe) *> (Join-Path $build 'gpp.log')
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $build 'gpp.log') -Tail 40;throw 'g++ failed'}
& $exe *> (Join-Path $build 'simulation.log')
$code=$LASTEXITCODE
Get-Content (Join-Path $build 'simulation.log')
if($code -ne 0){throw 'simulation failed'}
