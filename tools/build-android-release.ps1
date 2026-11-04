param([string]$Version = '0.1.2', [int]$BuildNumber = 3)
if ($Version -notmatch '^\d+\.\d+\.\d+$' -or $BuildNumber -lt 1) { throw 'Invalid release version' }
. (Join-Path $PSScriptRoot 'env.ps1')
& python (Join-Path $PSScriptRoot 'prepare-android-signing.py')
if ($LASTEXITCODE -ne 0) { throw 'Signing key preparation failed' }
$taskSigning = Get-Content -LiteralPath (Join-Path $env:VPNN_ROOT 'private\signing\android-release.json') -Raw | ConvertFrom-Json
$env:VPNN_ANDROID_KEYSTORE = $taskSigning.storeFile
$env:VPNN_ANDROID_STORE_PASSWORD = $taskSigning.storePassword
$env:VPNN_ANDROID_KEY_ALIAS = $taskSigning.keyAlias
$env:VPNN_ANDROID_KEY_PASSWORD = $taskSigning.keyPassword
Push-Location (Join-Path $env:VPNN_ROOT 'client')
try {
    & flutter build apk --release --split-per-abi --no-pub "--build-name=$Version" "--build-number=$BuildNumber" '--dart-define=SAFE_MODE=false'
    if ($LASTEXITCODE -ne 0) { throw 'Android release build failed' }
} finally {
    Pop-Location
    Remove-Item Env:\VPNN_ANDROID_STORE_PASSWORD,Env:\VPNN_ANDROID_KEY_PASSWORD -ErrorAction SilentlyContinue
}
