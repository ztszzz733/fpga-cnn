$ErrorActionPreference = 'Stop'
$waveExe = 'D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe'
$arguments = @('-f', ('"'+(Join-Path $PSScriptRoot 'two_small_control.vcd')+'"'), '-a', ('"'+(Join-Path $PSScriptRoot 'two_small_control.gtkw')+'"'), '-S', ('"'+(Join-Path $PSScriptRoot 'verify.tcl')+'"'))
$p = Start-Process -FilePath $waveExe -ArgumentList $arguments -WindowStyle Hidden -PassThru
if (-not $p.WaitForExit(60000)) { Stop-Process -Id $p.Id; throw 'GTKWave timeout' }
$v = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'validation.log') -Raw
if ($v -notmatch 'PASS GTKWave unique controls') { throw $v }
Write-Output $v
