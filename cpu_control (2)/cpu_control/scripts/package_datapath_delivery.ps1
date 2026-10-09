param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$upstreamRoot = (Resolve-Path (Join-Path $projectRoot "partners\datapath\upstream_20260917")).Path
$deliveryRoot = (Resolve-Path (Join-Path $projectRoot "partners\datapath\delivery")).Path

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $outputRoot = Join-Path $projectRoot "build\deliveries"
} else {
    $outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
}
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$upstreamFiles = @(Get-ChildItem -LiteralPath $upstreamRoot -Recurse -File | Sort-Object FullName)
$mismatches = @()
foreach ($sourceFile in $upstreamFiles) {
    $relative = $sourceFile.FullName.Substring($upstreamRoot.Length + 1)
    $candidate = Join-Path $deliveryRoot $relative
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        $mismatches += "MISSING $relative"
        continue
    }
    $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
    $candidateHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
    if ($sourceHash -ne $candidateHash) {
        $mismatches += "CHANGED $relative"
    }
}
if ($mismatches.Count -ne 0) {
    throw "负责人原始文件发生变化，停止打包：`n$($mismatches -join "`n")"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$stageRoot = Join-Path $outputRoot ("stage_datapath_b1_" + $stamp)
$packageName = "face_recognition_soc_datapath_b1_" + $stamp
$packageRoot = Join-Path $stageRoot $packageName
$zipPath = Join-Path $outputRoot ($packageName + ".zip")
New-Item -ItemType Directory -Path $packageRoot | Out-Null
Copy-Item -Path (Join-Path $deliveryRoot "*") -Destination $packageRoot -Recurse

$manifestPath = Join-Path $packageRoot "docs\datapath_delivery_sha256.txt"
$manifestLines = @()
$filesForManifest = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File |
    Where-Object { $_.FullName -ne $manifestPath } |
    Sort-Object FullName)
foreach ($file in $filesForManifest) {
    $relative = $file.FullName.Substring($packageRoot.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestLines += "$hash *$relative"
}
[System.IO.File]::WriteAllLines($manifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))

Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entryCount = $archive.Entries.Count
} finally {
    $archive.Dispose()
}

[pscustomobject]@{
    ZipPath = $zipPath
    ZipSha256 = $zipHash
    ArchiveEntries = $entryCount
    ProtectedOriginalFiles = $upstreamFiles.Count
    OriginalFilesChanged = 0
    StagingDirectory = $stageRoot
} | Format-List
