[CmdletBinding()]
param([switch]$NoDownload)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Artifact = @'
{"original_name":"character-windows-x64-0.4.0-dev1-candidate.zip","bytes":4491413065,"sha256":"92d3e858cb93471b1fe4e633e2b5328aa43dc178f325a9bfa65ca62d1405b7e3","source_commit":"d01ccc42bbe6795c216afae37dd0e53128ab58d9","download_base":"https://github.com/HarryShenwunai/AI-radio-stream-help/releases/download/v0.4.0-dev1-candidate/","parts":[{"name":"character-windows-x64-0.4.0-dev1-candidate.zip.part01","bytes":1610612736,"sha256":"b5b43075d0faf72ff0dbe87df8fe5dc434c06e4296b8f8b177715819f056cc9d","offset":0},{"name":"character-windows-x64-0.4.0-dev1-candidate.zip.part02","bytes":1610612736,"sha256":"19a6919e6c753f5cc82d9deddcb9de5919e37c7c848da1589355e189ce61d177","offset":1610612736},{"name":"character-windows-x64-0.4.0-dev1-candidate.zip.part03","bytes":1270187593,"sha256":"3cca5c00194ee35c58a600cdeddcaca5d02127931069f56d43b9610af29a7cda","offset":3221225472}],"windows_native_execution_verified":false,"cuda_offload_confirmed":false}
'@ | ConvertFrom-Json
$Root = $PSScriptRoot
$Lock = $null
$CurrentDownload = $null
$Assembling = $null
function Assert-Part($Path, $Part) {
    if ((Get-Item -LiteralPath $Path).Length -ne [Int64]$Part.bytes) { throw "Wrong file size: $($Part.name). Remove that damaged file and retry." }
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Part.sha256) { throw "SHA256 mismatch: $($Part.name). Remove that damaged file and retry." }
}
try {
    $LockPath = Join-Path $Root '.companion-download.lock'
    $Lock = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $Output = Join-Path $Root $Artifact.original_name
    if (Test-Path -LiteralPath $Output) {
        Assert-Part $Output ([pscustomobject]@{name=$Artifact.original_name; bytes=$Artifact.bytes; sha256=$Artifact.sha256})
        Write-Host "Verified existing archive: $Output"
        return
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    foreach ($Part in $Artifact.parts) {
        $Path = Join-Path $Root $Part.name
        if (-not (Test-Path -LiteralPath $Path)) {
            if ($NoDownload) { throw "Missing part: $($Part.name)" }
            $CurrentDownload = Join-Path $Root ($Part.name + '.' + [Guid]::NewGuid().ToString('N') + '.download')
            Write-Host "Downloading $($Part.name) ..."
            Invoke-WebRequest -Uri ($Artifact.download_base + $Part.name) -OutFile $CurrentDownload -UseBasicParsing -TimeoutSec 3600
            Assert-Part $CurrentDownload $Part
            [IO.File]::Move($CurrentDownload, $Path)
            $CurrentDownload = $null
        }
        Assert-Part $Path $Part
        Write-Host "Verified $($Part.name)"
    }
    $Assembling = Join-Path $Root ($Artifact.original_name + '.' + [Guid]::NewGuid().ToString('N') + '.assembling')
    $Writer = [IO.File]::Open($Assembling, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($Part in $Artifact.parts) {
            $Reader = [IO.File]::OpenRead((Join-Path $Root $Part.name))
            try { $Reader.CopyTo($Writer, 8MB) } finally { $Reader.Dispose() }
        }
        $Writer.Flush($true)
    } finally { $Writer.Dispose() }
    Assert-Part $Assembling ([pscustomobject]@{name=$Artifact.original_name; bytes=$Artifact.bytes; sha256=$Artifact.sha256})
    [IO.File]::Move($Assembling, $Output)
    $Assembling = $null
    Write-Host "SUCCESS: $Output"
    Write-Host 'Fully extract this ZIP, then run companion-desktop.exe inside the extracted folder.'
    Write-Host 'This is a Windows candidate; native Windows/GPU acceptance remains outstanding.'
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($CurrentDownload -and (Test-Path -LiteralPath $CurrentDownload)) { Remove-Item -LiteralPath $CurrentDownload -Force -ErrorAction SilentlyContinue }
    if ($Assembling -and (Test-Path -LiteralPath $Assembling)) { Remove-Item -LiteralPath $Assembling -Force -ErrorAction SilentlyContinue }
    if ($Lock) { $Lock.Dispose() }
}
