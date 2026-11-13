# Dot-sourced by build_windows_local.ps1 after its project-local tools are ready.
function Invoke-PortableRoute {
    $Report['route'] = 'verified-binaries-no-native-compiler'
    $Report['stage'] = 'prepare-assembly-tools'
    Run-Checked $python @('-m', 'pip', 'install', '--only-binary=:all:', 'packaging==26.3', 'setuptools', 'wheel', 'playwright', 'psutil')
    $NpmProject = Join-Path $Build 'npm-project'
    New-Item -ItemType Directory -Path $NpmProject -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root 'desktop\package.json') -Destination (Join-Path $NpmProject 'package.json') -Force
    Copy-Item -LiteralPath (Join-Path $Root 'desktop\package-lock.json') -Destination (Join-Path $NpmProject 'package-lock.json') -Force
    Run-Checked $npm @('ci', '--prefix', $NpmProject)
    $cpuRuntime = Join-Path $Build ('runtime-cpu-' + $Stamp)
    $cudaRuntime = Join-Path $Build ('runtime-cuda-' + $Stamp)
    $runtimeCache = Join-Path $Build 'runtime-cache'
    $Report['stage'] = 'assemble-CPU-runtime'
    Run-Checked $python @('scripts/build_windows_embedded.py', '--profile', 'cpu', '--output', $cpuRuntime, '--cache', $runtimeCache)
    if (!$CpuOnly) {
        $Report['stage'] = 'assemble-CUDA-runtime'
        Run-Checked $python @('scripts/build_windows_embedded.py', '--profile', 'cuda', '--output', $cudaRuntime, '--cache', $runtimeCache)
    }
    $runtimePython = Join-Path $cpuRuntime 'python\python.exe'
    $Report['stage'] = 'native-preflight'
    $nativeProbe = 'import ctypes;from PIL import Image;import llama_cpp,onnxruntime,kokoro_onnx,espeakng_loader,faster_whisper,ctranslate2,av,aiohttp,brotli;ctypes.CDLL(espeakng_loader.get_library_path());print(''Windows native dependency imports passed'')'
    try { Run-Checked $runtimePython @('-I', '-X', 'utf8', '-c', $nativeProbe) }
    catch {
        Write-Host 'Missing MSVCP140/MSVCP140_1/VCOMP140: review the official Microsoft Visual C++ x64 runtime instructions:'
        Write-Host 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist'
        Write-Host 'No global runtime or driver was installed automatically.'
        throw
    }
    $Report['native_dependency_imports_verified'] = $true
    $Report['stage'] = 'engineering-quality-gates'
    Run-Checked $python @('scripts/quality_gate.py', '--bootstrap', '--full', '--test-python', $runtimePython, '--report', (Join-Path $Results 'quality-gate.json'))
    $Release = Join-Path $Build ('releases\' + $Stamp)
    $Package = Join-Path $Release 'character-windows-x64'
    $assembly = @('scripts/assemble_windows_release.py', '--cpu-backend', $cpuRuntime, '--electron-dist', (Join-Path $NpmProject 'node_modules\electron\dist'), '--node', $node, '--output', $Package)
    if (!$CpuOnly) { $assembly += @('--cuda-backend', $cudaRuntime) }
    if (!$WithoutModels) {
        $Report['stage'] = 'verified-model-assets'
        $AssetCache = Join-Path $Build 'model-assets'
        New-Item -ItemType Directory -Path $AssetCache -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $Root 'app\download_models.py') -Destination (Join-Path $AssetCache 'download_models.py') -Force
        foreach ($relative in @('models\qwen3-4b-instruct-2507-q4_k_m.gguf', 'voices\kokoro-v1.0.onnx', 'voices\voices-v1.0.bin')) {
            $cached = Join-Path $AssetCache $relative; $existing = Join-Path (Join-Path $Root 'app') $relative
            if (!(Test-Path $cached) -and (Test-Path $existing)) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $cached) -Force | Out-Null
                Copy-Item -LiteralPath $existing -Destination $cached
            }
        }
        Run-Checked $runtimePython @('-I', '-X', 'utf8', (Join-Path $AssetCache 'download_models.py'))
        $tiny = Join-Path $AssetCache 'models\asr\faster-whisper-tiny'
        Run-Checked $runtimePython @('-I', '-X', 'utf8', '-m', 'companion_runtime.voice', 'download', '--model', 'tiny', '--directory', $tiny)
        $assembly += @('--models', (Join-Path $AssetCache 'models'), '--voices', (Join-Path $AssetCache 'voices'), '--asr', $tiny)
    }
    $Report['stage'] = 'assemble-portable'
    Run-Checked $python $assembly
    Run-Checked $runtimePython @('-I', '-X', 'utf8', 'scripts/windows_device_diagnostics.py', '--output', (Join-Path $Results 'hardware.json'))
    $env:COMPANION_DESKTOP_BINARY = Join-Path $Package 'companion-desktop.exe'
    $env:COMPANION_DESKTOP_SCREENSHOTS = $Results
    $Report['stage'] = 'actual-Windows-GUI-smoke'
    Run-Checked $python @('desktop/test/windows_smoke.py')
    $Report['windows_execution_verified'] = $true
    $Report['scope'] = 'This machine native imports and synthetic GUI/PNG/window smoke; CUDA offload, voice quality and real accounts remain separate'
    $Report['status'] = 'passed'; $Report['stage'] = 'ready-to-run'; $Report['package_directory'] = $Package
    $Report['completed_at'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-JsonFile (Join-Path $Package 'BUILD-INFO.json') $Report
    Write-JsonFile (Join-Path $Logs ('build-' + $Stamp + '.json')) $Report
    [IO.File]::WriteAllText((Join-Path $Build 'LAST-BUILD.txt'), $Package, $Utf8)
    Write-Host ('READY: ' + (Join-Path $Package 'companion-desktop.exe')) -ForegroundColor Green
    Write-Host 'No native compilation required. Missing VC++ prerequisites are reported, never installed silently.'
    if (!$NoOpen) {
        if ($null -eq $OriginalCompanionData) { Remove-Item Env:COMPANION_DATA -ErrorAction SilentlyContinue } else { $env:COMPANION_DATA = $OriginalCompanionData }
        Start-Process -FilePath (Join-Path $Package 'companion-desktop.exe') -WorkingDirectory $Package
    }
}
