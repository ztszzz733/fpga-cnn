[CmdletBinding()]
param(
    [ValidateSet('Apply', 'Check', 'Cli', 'Desktop')]
    [string]$Mode = 'Apply'
)

$taskProxy = Import-PowerShellDataFile -LiteralPath (Join-Path $PSScriptRoot 'proxy.psd1')
foreach ($taskProxyName in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')) {
    if (-not $taskProxy[$taskProxyName]) { throw "Missing proxy setting: $taskProxyName" }
    [Environment]::SetEnvironmentVariable($taskProxyName, $taskProxy[$taskProxyName], 'Process')
}
$taskProjectRoot = Split-Path -Parent $PSScriptRoot

switch ($Mode) {
    'Apply' {
        Write-Host "Proxy applied to this PowerShell process: $($taskProxy.HTTPS_PROXY)"
    }
    'Check' {
        $taskCurl = Get-Command curl.exe -ErrorAction Stop
        # No API key is sent. HTTP 401 is the expected unauthenticated response.
        $taskStatus = & $taskCurl.Source --proxy $taskProxy.HTTPS_PROXY --connect-timeout 5 --max-time 15 --silent --show-error --output NUL --write-out '%{http_code}' 'https://api.openai.com/v1/models'
        if ($LASTEXITCODE -ne 0) { throw 'Proxy connection or TLS verification failed.' }
        if ($taskStatus -ne '401') { throw "Unexpected HTTP status: $taskStatus. This does not confirm a working Codex session." }
        Write-Host 'Proxy HTTPS check passed (HTTP 401; no credentials sent).'
    }
    'Cli' {
        $taskCodex = Get-Command codex.exe -ErrorAction Stop
        & $taskCodex.Source -C $taskProjectRoot
        if ($LASTEXITCODE -ne 0) { throw "Codex exited with code $LASTEXITCODE" }
    }
    'Desktop' {
        $taskPackage = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
        if (-not $taskPackage) { throw 'The OpenAI.Codex desktop package was not found.' }
        $taskAppPath = Join-Path $taskPackage.InstallLocation 'app\ChatGPT.exe'
        if (-not (Test-Path -LiteralPath $taskAppPath)) { throw 'Desktop executable was not found.' }
        $taskRunning = Get-Process -Name ChatGPT -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskAppPath }
        if ($taskRunning) { throw 'Codex desktop is already running. Save your work and fully quit it before using this launcher; it will not be stopped automatically.' }
        Start-Process -FilePath $taskAppPath -WorkingDirectory $taskProjectRoot -WindowStyle Hidden
        Write-Host 'Desktop launched with proxy environment variables. Open the cpu_control project in the app.'
    }
}
