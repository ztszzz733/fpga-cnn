param(
    [int]$Size = 11,
    [int]$InputChannels = 3,
    [int]$OutputChannels = 3,
    [int]$Repeats = 1,
    [string[]]$Cases = @('neureka'),
    [string]$Reuse = '',
    [switch]$Waves,
    [string]$Distro = 'Ubuntu-22.04'
)
$ErrorActionPreference = 'Stop'
$scriptFile = Join-Path $PSScriptRoot 'run_neureka_benchmark.py'
$linuxScript = (& wsl -d $Distro -- wslpath -a $scriptFile | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve WSL project path.' }
$simArgs = @('-d',$Distro,'--','python3',$linuxScript,'--size',"$Size",'--ci',"$InputChannels",'--co',"$OutputChannels",'--repeats',"$Repeats",'--cases') + $Cases
if ($Reuse) {
    $resolvedReuse = (Resolve-Path -LiteralPath $Reuse).Path
    $linuxReuse = (& wsl -d $Distro -- wslpath -a $resolvedReuse | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve reusable simulation path.' }
    $simArgs += @('--reuse',$linuxReuse)
}
if ($Waves) { $simArgs += '--waves' }
& wsl @simArgs
exit $LASTEXITCODE
