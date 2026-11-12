param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = 'mover23_top_waveform_20261111'
$manifest = Join-Path $root "$name.parts.sha256"
$zip = Join-Path $root "$name.zip"
$expectedZipHash = ((Get-Content -LiteralPath (Join-Path $root "$name.zip.sha256") -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$records = @(Get-Content -LiteralPath $manifest | Where-Object { $_.Trim() })
if ($records.Count -ne 5) { throw "Expected five parts; found $($records.Count)." }

$parts = foreach ($record in $records) {
    if ($record -notmatch '^([0-9a-fA-F]{64})\s+(.+)$') { throw "Invalid manifest entry: $record" }
    $expectedPartHash = $Matches[1].ToLowerInvariant()
    $partName = $Matches[2]
    if ($partName -notmatch '^mover23_top_waveform_20261111\.zip\.part\d{2}$') { throw "Unexpected part name: $partName" }
    $part = Join-Path $root $partName
    if (-not (Test-Path -LiteralPath $part -PathType Leaf)) { throw "Missing part: $partName" }
    $actual = (Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expectedPartHash) { throw "Hash mismatch: $partName" }
    $part
}

if (-not (Test-Path -LiteralPath $zip -PathType Leaf) -or
    (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedZipHash) {
    $output = [System.IO.File]::Open($zip, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    try {
        foreach ($part in $parts) {
            $inputStream = [System.IO.File]::OpenRead($part)
            try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
        }
    } finally { $output.Dispose() }
}
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedZipHash) {
    throw 'Reassembled ZIP hash mismatch.'
}
if ($VerifyOnly) { Write-Output 'PASS: all parts and the reassembled ZIP match SHA-256'; return }

$packageDir = Join-Path $root $name
$launcher = Join-Path $packageDir 'open_top_waveform.cmd'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    Expand-Archive -LiteralPath $zip -DestinationPath $root -Force
}
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Package launcher is missing after extraction.' }
Start-Process -FilePath $launcher -WorkingDirectory $packageDir
