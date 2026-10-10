param([int]$Width=524,[int]$Height=524,[int]$Frames=6,[int]$Chunk=1024,[int]$Fault=0,[switch]$Waves)
$ErrorActionPreference='Stop'
$streamScript=Join-Path $PSScriptRoot 'run_stream_integration.py'
$streamLinux=(& wsl -d Ubuntu-22.04 -- wslpath -a $streamScript | Select-Object -Last 1).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot resolve WSL path'}
$streamArgs=@('-d','Ubuntu-22.04','--','python3',$streamLinux,'--width',"$Width",'--height',"$Height",'--frames',"$Frames",'--chunk',"$Chunk",'--fault',"$Fault")
if($Waves){$streamArgs+='--waves'}
& wsl @streamArgs
exit $LASTEXITCODE
