$ErrorActionPreference = 'Stop'
$waveExe = 'D:\code\FPGA1\cpu_control (2)\cpu_control\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe'
foreach ($viewName in @('full','pw8_detail')) {
 $dumpName = if ($viewName -eq 'full') { 'control.fst' } else { 'control_detail.fst' }
 $gtkwArguments = @('-f', ('"'+(Join-Path $PSScriptRoot $dumpName)+'"'), '-a', ('"'+(Join-Path $PSScriptRoot ($viewName+'.gtkw'))+'"'), '-S', ('"'+(Join-Path $PSScriptRoot ('verify_'+$viewName+'.tcl'))+'"'))
 $waveProcess = Start-Process -FilePath $waveExe -ArgumentList $gtkwArguments -WindowStyle Hidden -PassThru
 if (-not $waveProcess.WaitForExit(60000)) { Stop-Process -Id $waveProcess.Id; throw 'GTKWave verification timeout' }
 $verification = Get-Content -LiteralPath (Join-Path $PSScriptRoot ('validation_'+$viewName+'.log')) -Raw
 if ($verification -notmatch 'PASS GTKWave unique controls') { throw $verification }
 Write-Output $verification
}
