param(
    [string]$Distro = 'Ubuntu-22.04',
    [int]$Seed = 1,
    [string[]]$Cases = @('original','serial','overlap','one_bank','memory','restart'),
    [switch]$Waves,
    [switch]$TopWaves
)
$ErrorActionPreference = 'Stop'
$scriptFile = Join-Path $PSScriptRoot 'run_overlap_integration.py'
$linuxScript = (& wsl -d $Distro -- wslpath -a $scriptFile | Select-Object -Last 1).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the WSL project path.' }
$simArgs = @('-d',$Distro,'--','python3',$linuxScript,'--simulator','verilator','--seed',"$Seed",'--cases') + $Cases
if ($Waves) { $simArgs += '--waves' }
if ($TopWaves) { $simArgs += '--top-waves' }
& wsl @simArgs
exit $LASTEXITCODE
