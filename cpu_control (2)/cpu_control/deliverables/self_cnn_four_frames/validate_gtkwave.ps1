$ErrorActionPreference='Stop'
$artifactRoot=$PSScriptRoot
$gtkExe=(Resolve-Path -LiteralPath (Join-Path $artifactRoot '..\..\tools\gtkwave\portable\gtkwave64\bin\gtkwave.exe')).Path
$views=@('overview','input','mac','result')
$results=@()
foreach($view in $views){
  $logPath=Join-Path $artifactRoot ('validation_'+$view+'.log')
  if(Test-Path -LiteralPath $logPath){Remove-Item -LiteralPath $logPath}
  $arguments=@('-f','overlap/control.vcd','-a',($view+'.gtkw'),'-S',('verify_'+$view+'.tcl'))
  $process=Start-Process -FilePath $gtkExe -ArgumentList $arguments -WorkingDirectory $artifactRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactRoot ('gtk_'+$view+'_stdout.log')) -RedirectStandardError (Join-Path $artifactRoot ('gtk_'+$view+'_stderr.log'))
  $exited=$process.WaitForExit(20000)
  if(-not $exited){Stop-Process -Id $process.Id}
  $contents=if(Test-Path -LiteralPath $logPath){Get-Content -LiteralPath $logPath -Raw}else{''}
  $status=if($exited -and $process.ExitCode -eq 0 -and $contents.Contains('PASS '+$view) -and $contents.Contains('SIGNALS=25 UNIQUE=25')){'PASS'}else{'FAIL'}
  $results += [pscustomobject]@{view=$view;status=$status;exited=$exited;signals=25;unique_signals=25;session_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot ($view+'.gtkw')) -Algorithm SHA256).Hash.ToLower();log=$contents.Trim()}
  Write-Output ($view+' '+$status)
}
$allPass=(@($results | Where-Object {$_.status -ne 'PASS'}).Count -eq 0)
[pscustomobject]@{status=$(if($allPass){'PASS'}else{'FAIL'});tool='GTKWave 3.3.100 actual Tcl validation';vcd_sha256=(Get-FileHash -LiteralPath (Join-Path $artifactRoot 'overlap\control.vcd') -Algorithm SHA256).Hash.ToLower();views=$results} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $artifactRoot 'gtkwave_validation.json') -Encoding UTF8
if(-not $allPass){exit 1}
