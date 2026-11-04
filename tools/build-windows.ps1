param([ValidateSet('debug','release')][string]$Mode = 'debug')
. (Join-Path $PSScriptRoot 'env.ps1')
Push-Location (Join-Path $env:VPNN_ROOT 'client')
try {
    & flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Dependency resolution failed' }
    & flutter build windows "--$Mode" '--no-pub' '--dart-define=SAFE_MODE=true'
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
} finally {
    Pop-Location
}
