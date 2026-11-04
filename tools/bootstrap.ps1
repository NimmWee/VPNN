$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'checkout-sources.ps1')
& python -u (Join-Path $PSScriptRoot 'bootstrap_toolchains.py')
if ($LASTEXITCODE -ne 0) { throw 'Toolchain installation failed' }
& python -u (Join-Path $PSScriptRoot 'install_native_tools.py')
if ($LASTEXITCODE -ne 0) { throw 'Native toolchain installation failed' }
& python -u (Join-Path $PSScriptRoot 'install_llvm.py')
if ($LASTEXITCODE -ne 0) { throw 'LLVM bindgen installation failed' }
. (Join-Path $PSScriptRoot 'env.ps1')
$taskSdkManager = Join-Path $env:ANDROID_HOME 'cmdline-tools\19.0\bin\sdkmanager.bat'
1..200 | ForEach-Object { 'y' } | & $taskSdkManager --sdk_root=$env:ANDROID_HOME --licenses
if ($LASTEXITCODE -ne 0) { throw 'SDK license setup failed' }
& python -u (Join-Path $PSScriptRoot 'install_android_packages.py')
if ($LASTEXITCODE -ne 0) { throw 'SDK package installation failed' }
Push-Location (Join-Path $taskRoot 'client')
try {
    & flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Flutter dependency resolution failed' }
} finally {
    Pop-Location
}
Write-Output 'SDKs and source prepared. Run tools\doctor.ps1, then build Windows and Android sequentially.'
