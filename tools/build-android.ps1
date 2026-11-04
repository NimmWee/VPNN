. (Join-Path $PSScriptRoot 'env.ps1')
Push-Location (Join-Path $env:VPNN_ROOT 'client')
try {
    & flutter build apk --debug --target-platform android-x64 --no-pub '--dart-define=SAFE_MODE=true'
    if ($LASTEXITCODE -ne 0) { throw 'Android emulator build failed' }
} finally {
    Pop-Location
}
