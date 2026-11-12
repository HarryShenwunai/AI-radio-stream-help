# Windows PowerShell 5.1 compatible. This script changes only its own process
# environment and generated files below the project's .build directory.
[CmdletBinding()]
param([switch]$WithoutModels, [switch]$NoOpen, [switch]$NativeCompile, [switch]$CpuOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root '.build\windows-local'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Logs = Join-Path $Build 'logs'
$Downloads = Join-Path $Build 'downloads'
$Tools = Join-Path $Build 'tools'
$Utf8 = [Text.UTF8Encoding]::new($false)
$Report = [ordered]@{ status = 'running'; stage = 'preflight'; started_at = (Get-Date).ToUniversalTime().ToString('o'); models_included = !$WithoutModels; windows_execution_verified = $false }
$TranscriptStarted = $false
$OriginalCompanionData = $env:COMPANION_DATA

function Write-JsonFile([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), $Utf8)
}
function Run-Checked([string]$File, [string[]]$Arguments) {
    Write-Host ('> ' + $File + ' ' + ($Arguments -join ' '))
    # PS5.1 represents native stderr as ErrorRecord even for normal progress.
    # Capture it without treating a warning as failure; exit status is decisive.
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = $null
        & $File @Arguments 2>&1 | Out-Host
        $result = $global:LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($null -eq $result) { throw ('Command could not be started or did not return an exit code: ' + $File) }
    if ($result -ne 0) { throw ('Command failed with exit code ' + $result + ': ' + $File) }
}
function Get-VerifiedArtifact($Artifact) {
    if ($Artifact.sha256 -notmatch '^[a-f0-9]{64}$' -or !([Uri]$Artifact.url).IsAbsoluteUri -or ([Uri]$Artifact.url).Scheme -ne 'https') {
        throw 'Tool manifest contains an invalid HTTPS URL or SHA256.'
    }
    $destination = Join-Path $Downloads $Artifact.filename
    if (Test-Path -LiteralPath $destination) {
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Artifact.sha256) { return $destination }
        throw ('Cached download has a wrong SHA256. Move it aside and retry: ' + $destination)
    }
    $partial = $destination + '.part'
    Write-Host ('Downloading verified artifact: ' + $Artifact.url)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Artifact.url -OutFile $partial
            break
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host ('Download interrupted; retry ' + ($attempt + 1) + '/3')
            Start-Sleep -Seconds 2
        }
    }
    $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Artifact.sha256) { throw ('SHA256 mismatch; artifact will not be executed: ' + $partial) }
    Move-Item -LiteralPath $partial -Destination $destination
    return $destination
}
function Probe-Python([string]$File, [string[]]$PrefixArguments = @()) {
    try {
        if ($File -like '*\WindowsApps\*') { return $null }
        # Single quotes inside the Python program survive legacy PS5.1 native
        # argument quoting (embedded double quotes do not reliably survive).
        $line = & $File @PrefixArguments -c "import json,struct,sys;print(json.dumps({'major':sys.version_info.major,'minor':sys.version_info.minor,'bits':struct.calcsize('P')*8,'executable':sys.executable,'version':sys.version}))" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $info = ($line -join '') | ConvertFrom-Json
        if ($info.major -eq 3 -and $info.minor -ge 10 -and $info.minor -le 12 -and $info.bits -eq 64) { return $info }
    } catch { }
    return $null
}
function Get-BuildPython {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($minor in @('3.12', '3.11', '3.10')) {
            $found = Probe-Python $launcher.Source @('-' + $minor)
            if ($found -and $found.minor -ge 11) { return $found }
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) {
            $found = Probe-Python $candidate.Source
            if ($found -and $found.minor -ge 11) { return $found }
        }
    }
    Write-Host 'Pillow 13 needs Python >=3.11 and Misaki needs <3.13; detected Python 3.10 is not used for this build.'
    Write-Host 'Preparing project-local Astral uv and managed CPython 3.12 (python-build-standalone).'
    $archive = Get-VerifiedArtifact $Manifest.uv
    $uvDirectory = Join-Path $Tools ('uv-' + $Manifest.uv.version)
    Expand-Archive -LiteralPath $archive -DestinationPath $uvDirectory -Force
    $uv = Join-Path $uvDirectory 'uv.exe'
    if (!(Test-Path -LiteralPath $uv)) { throw 'Verified uv archive did not contain uv.exe.' }
    Run-Checked $uv @('python', 'install', '3.12', '--upgrade', '--no-registry', '--no-bin', '--no-config')
    $managed = & $uv python find --managed-python 3.12 --no-project --no-config
    if ($LASTEXITCODE -ne 0) { throw 'uv did not return a managed Python 3.12 interpreter.' }
    $found = Probe-Python (($managed -join '').Trim())
    if (!$found) { throw 'Managed Python is not compatible Windows x64 Python 3.10-3.12.' }
    $Report['python_distribution'] = 'Astral python-build-standalone CPython 3.12; downloaded and verified by pinned uv'
    return $found
}
function Get-BuildNode {
    $candidate = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($candidate) {
        try {
            $info = (& $candidate.Source -p "JSON.stringify({major:Number(process.versions.node.split('.')[0]),arch:process.arch,version:process.versions.node})") | ConvertFrom-Json
            if ($LASTEXITCODE -eq 0 -and $info.major -ge 22 -and $info.arch -eq 'x64' -and (Test-Path (Join-Path (Split-Path $candidate.Source) 'npm.cmd'))) { return $candidate.Source }
        } catch { }
    }
    Write-Host 'Preparing the official project-local Node.js 22 portable runtime.'
    $archive = Get-VerifiedArtifact $Manifest.node
    Expand-Archive -LiteralPath $archive -DestinationPath $Tools -Force
    $node = Join-Path $Tools ('node-v' + $Manifest.node.version + '-win-x64\node.exe')
    if (!(Test-Path -LiteralPath $node)) { throw 'Verified Node archive did not contain the expected node.exe.' }
    return $node
}

try {
    if ($env:OS -ne 'Windows_NT' -or ![Environment]::Is64BitOperatingSystem -or ![Environment]::Is64BitProcess) {
        throw 'Run build-windows.cmd from 64-bit Windows 10/11 x64. ARM and 32-bit builds are unsupported.'
    }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { throw 'This build targets x64 PCs; ARM64 native/emulated Windows is not verified.' }
    # Read the actual build number; legacy .NET OSVersion can report a
    # compatibility version if its application manifest is not Windows-aware.
    $WindowsBuild = [int](Get-ItemPropertyValue -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name 'CurrentBuildNumber')
    if ($WindowsBuild -lt 10240) { throw 'Windows 10 or later is required.' }
    $Report['windows_build'] = $WindowsBuild
    foreach ($directory in @($Build, $Logs, $Downloads, $Tools, (Join-Path $Build 'temp'))) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
    $LogPath = Join-Path $Logs ('build-' + $Stamp + '.log')
    Start-Transcript -LiteralPath $LogPath | Out-Null
    $TranscriptStarted = $true
    Write-Host ('Project: ' + $Root)
    Write-Host ('Build log: ' + $LogPath)
    Write-Host 'The first build downloads dependencies and several GB of verified models; keep this window open.'
    Write-Host 'This script does not request elevation, change system PATH or access GitHub billing.'
    Write-Host 'If required Visual C++ runtime DLLs are missing, it stops with the official prerequisite instructions.'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Set-Location -LiteralPath $Root
    $Manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-build-tools.json') -Raw | ConvertFrom-Json
    # Every assignment affects this process and its children only.
    $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONUNBUFFERED = '1'
    $env:PYTHONNOUSERSITE = '1'; $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PIP_CACHE_DIR = Join-Path $Build 'pip-cache'; $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:npm_config_cache = Join-Path $Build 'npm-cache'
    $env:ELECTRON_CACHE = Join-Path $Build 'electron-cache'
    $env:XDG_CACHE_HOME = Join-Path $Build 'cache'
    $env:UV_CACHE_DIR = Join-Path $Build 'uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Build 'python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $Build 'python-bin'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'; $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_NO_PROGRESS = '1'
    $env:TEMP = Join-Path $Build 'temp'; $env:TMP = $env:TEMP
    $Report['stage'] = 'prepare-tools'
    $basePython = Get-BuildPython
    $node = Get-BuildNode
    $nodeDirectory = Split-Path -Parent $node
    $npm = Join-Path $nodeDirectory 'npm.cmd'
    $env:PATH = $nodeDirectory + ';' + $env:PATH
    $venv = Join-Path $Build 'venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    if (!(Test-Path -LiteralPath $python)) { Run-Checked $basePython.executable @('-m', 'venv', $venv) }
    $pythonInfo = Probe-Python $python
    if (!$pythonInfo -or $pythonInfo.minor -lt 11) { throw ('Existing build venv needs x64 Python 3.11/3.12 for the pinned dependencies. Rename this generated directory and retry: ' + $venv) }
    $Report['python'] = $pythonInfo.version
    $Report['node'] = (& $node --version | Out-String).Trim()
    $env:PATH = (Join-Path $venv 'Scripts') + ';' + $env:PATH
    $env:PIP_REQUIRE_VIRTUALENV = '1'
    $env:COMPANION_DATA = Join-Path $Build 'unused-build-data'
    $Results = Join-Path $Logs ('results-' + $Stamp)
    $env:COMPANION_REPORT_DIR = $Results
    $env:COMPANION_DESKTOP_TEST_RESULTS = $Results
    if (!$NativeCompile) {
        . (Join-Path $PSScriptRoot 'windows_portable_route.ps1')
        Invoke-PortableRoute
        return
    }
    $Report['stage'] = 'install-dependencies'
    Run-Checked $python @('-m', 'pip', 'install', '--upgrade', 'pip')
    $wheel = Get-VerifiedArtifact $Manifest.llama_cpu_wheel
    Run-Checked $python @('-m', 'pip', 'install', '--no-deps', $wheel)
    Run-Checked $python @('-m', 'pip', 'install', '--prefer-binary', '--only-binary=llama-cpp-python', '-r', 'app/requirements-core.txt', '-r', 'app/requirements.txt', '-r', 'app/requirements-voice.txt', '-r', 'src/companion_runtime/connectors/requirements.txt', '-r', 'requirements-dev.txt', 'pyinstaller==6.22.3', 'psutil==7.0.0')
    Run-Checked $python @('-m', 'pip', 'check')
    $Report['stage'] = 'native-dll-preflight'
    $importScript = @'
import ctypes,sys
try:
    from PIL import Image
    import llama_cpp,onnxruntime,kokoro_onnx,espeakng_loader
    ctypes.CDLL(espeakng_loader.get_library_path())
    print('Pillow, llama.cpp, ONNX Runtime, Kokoro and eSpeak native imports passed.')
except Exception as error:
    print('Native dependency preflight failed:',repr(error),file=sys.stderr)
    print('If MSVCP140.dll, MSVCP140_1.dll or VCOMP140.dll is missing, review the official Microsoft Visual C++ x64 prerequisite:',file=sys.stderr)
    print('https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist',file=sys.stderr)
    print('The build script will not install system runtimes or change system configuration.',file=sys.stderr)
    raise SystemExit(1)
'@
    Run-Checked $python @('-c', $importScript)
    $NpmProject = Join-Path $Build 'npm-project'
    New-Item -ItemType Directory -Path $NpmProject -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root 'desktop\package.json') -Destination (Join-Path $NpmProject 'package.json') -Force
    Copy-Item -LiteralPath (Join-Path $Root 'desktop\package-lock.json') -Destination (Join-Path $NpmProject 'package-lock.json') -Force
    Run-Checked $npm @('ci', '--prefix', $NpmProject)
    $Report['stage'] = 'regression-tests'
    Run-Checked $python @('scripts/quality_gate.py', '--bootstrap', '--full', '--report', (Join-Path $Results 'quality-gate.json'))
    Run-Checked $python @('scripts/check.py')
    Run-Checked $node @('tests/test_character_ui.mjs')
    Run-Checked $node @('tests/test_voice_ui.mjs')
    Run-Checked $npm @('test', '--prefix', 'desktop')
    $Report['stage'] = 'compile-backend'
    Run-Checked $python @('scripts/build_backend_windows.py')
    Run-Checked $python @('scripts/native_character_check.py')
    $Report['stage'] = 'assemble-and-test-desktop'
    $Release = Join-Path $Build ('releases\' + $Stamp)
    $Package = Join-Path $Release 'character-windows-x64'
    New-Item -ItemType Directory -Path $Release -Force | Out-Null
    Run-Checked $node @('desktop/build-windows.cjs', '--backend=.build/native/companion-backend', ('--electron-dist=' + (Join-Path $NpmProject 'node_modules\electron\dist')), ('--output=' + $Package))
    $env:COMPANION_DESKTOP_BINARY = Join-Path $Package 'companion-desktop.exe'
    $env:COMPANION_DESKTOP_SCREENSHOTS = $Results
    Run-Checked $python @('desktop/test/windows_smoke.py')
    $Report['windows_execution_verified'] = $true
    $Report['stage'] = 'verified-model-assets'
    if (!$WithoutModels) {
        $AssetCache = Join-Path $Build 'model-assets'
        New-Item -ItemType Directory -Path $AssetCache -Force | Out-Null
        # Run the existing pinned downloader unchanged from a project-local
        # cache directory, so it also keeps its GB-sized outputs under .build.
        Copy-Item -LiteralPath (Join-Path $Root 'app\download_models.py') -Destination (Join-Path $AssetCache 'download_models.py') -Force
        foreach ($relative in @('models\qwen3-4b-instruct-2507-q4_k_m.gguf', 'voices\kokoro-v1.0.onnx', 'voices\voices-v1.0.bin')) {
            $cached = Join-Path $AssetCache $relative
            $existing = Join-Path (Join-Path $Root 'app') $relative
            if (!(Test-Path $cached) -and (Test-Path $existing)) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $cached) -Force | Out-Null
                Copy-Item -LiteralPath $existing -Destination $cached
            }
        }
        Run-Checked $python @((Join-Path $AssetCache 'download_models.py'))
        $PackBackend = Join-Path $Package 'resources\backend'
        Copy-Item -LiteralPath (Join-Path $AssetCache 'models') -Destination (Join-Path $PackBackend 'models') -Recurse
        Copy-Item -LiteralPath (Join-Path $AssetCache 'voices') -Destination (Join-Path $PackBackend 'voices') -Recurse
        $env:COMPANION_MODELS = Join-Path $PackBackend 'models'
        $env:COMPANION_VOICES = Join-Path $PackBackend 'voices'
        $Report['stage'] = 'actual-local-inference-and-speech'
        # The Electron smoke has exited; do not run it concurrently with the LLM.
        Run-Checked $python @('scripts/native_character_check.py', '--binary', (Join-Path $PackBackend 'companion-backend.exe'), '--with-model')
    }
    $Report['stage'] = 'package-and-hash'
    $Report['source_commit'] = $null
    if ((Test-Path (Join-Path $Root '.git')) -and (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        $commit = & git.exe -C $Root rev-parse HEAD
        if ($LASTEXITCODE -eq 0 -and ($commit -join '') -match '^[a-f0-9]{40}$') {
            $Report['source_commit'] = ($commit -join '')
            $Report['source_worktree_dirty'] = [bool](& git.exe -C $Root status --porcelain)
        }
    }
    $SourceFiles = @('app\server.py', 'app\requirements-core.txt', 'app\requirements.txt', 'run.py', 'desktop\package.json', 'desktop\package-lock.json') | ForEach-Object { Get-Item -LiteralPath (Join-Path $Root $_) }
    foreach ($folder in @('app\static', 'src', 'scripts')) { $SourceFiles += Get-ChildItem -LiteralPath (Join-Path $Root $folder) -File -Recurse | Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' } }
    $SourceFiles += Get-ChildItem -LiteralPath (Join-Path $Root 'desktop') -Filter '*.cjs' -File
    $sourceHashes = $SourceFiles | Sort-Object FullName -Unique | ForEach-Object { ((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()) + '  ' + $_.FullName.Substring($Root.Length + 1).Replace('\', '/') }
    [IO.File]::WriteAllLines((Join-Path $Package 'SOURCE-SHA256SUMS.txt'), [string[]]$sourceHashes, $Utf8)
    $Report['source_manifest_sha256'] = (Get-FileHash (Join-Path $Package 'SOURCE-SHA256SUMS.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
    $Report['source_repository'] = 'https://github.com/HarryShenwunai/AI-radio-stream-help'
    $Report['code_signed'] = $false
    $Report['status'] = 'validated-package-contents'
    $Report['stage'] = 'ready-for-archive'
    $Report['completed_at'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-JsonFile (Join-Path $Package 'BUILD-INFO.json') $Report
    $ZipPath = Join-Path $Release ('character-windows-x64-' + $(if ($WithoutModels) { 'runtime' } else { 'offline' }) + '.zip')
    # zipfile supports ZIP64 and >2GiB individual model files; PS5.1
    # Compress-Archive does not reliably support this use case.
    $zipScript = @'
from pathlib import Path
import os,sys,zipfile
root=Path(sys.argv[1]); target=Path(sys.argv[2]); temporary=target.with_suffix('.zip.part')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file(): archive.write(path,path.relative_to(root.parent).as_posix())
os.replace(temporary,target)
print('Created ZIP64 package:',target)
'@
    Run-Checked $python @('-c', $zipScript, $Package, $ZipPath)
    $ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(($ZipPath + '.sha256'), ($ZipHash + '  ' + (Split-Path $ZipPath -Leaf) + "`n"), $Utf8)
    $Report['package'] = $ZipPath; $Report['package_sha256'] = $ZipHash
    $Report['status'] = 'passed'; $Report['stage'] = 'complete'
    Write-JsonFile (Join-Path $Logs ('build-' + $Stamp + '.json')) $Report
    [IO.File]::WriteAllText((Join-Path $Build 'LAST-BUILD.txt'), $ZipPath, $Utf8)
    Write-Host ''
    Write-Host ('BUILD PASSED: ' + $ZipPath) -ForegroundColor Green
    Write-Host ('SHA256: ' + $ZipHash)
    Write-Host ('Unpacked executable: ' + (Join-Path $Package 'companion-desktop.exe'))
    Write-Host 'This is a local machine observation, not certification of every Windows configuration or voice quality.'
    if (!$NoOpen) {
        try { Start-Process explorer.exe -ArgumentList @($Release) | Out-Null }
        catch { Write-Host ('Package is complete; open the output folder manually: ' + $Release) }
    }
} catch {
    $Report['status'] = 'failed'; $Report['error'] = $_.Exception.Message
    if (Test-Path -LiteralPath $Logs) { Write-JsonFile (Join-Path $Logs ('build-' + $Stamp + '.json')) $Report }
    Write-Host ('BUILD STOPPED at ' + $Report['stage'] + ': ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Logs and completed intermediate files are preserved in: ' + $Build)
    Write-Host 'No successful final package is claimed. Fix the reported issue and run build-windows.cmd again.'
    exit 1
} finally {
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
}
