$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskClient = Join-Path $taskRoot 'client'
if (-not (Test-Path -LiteralPath (Join-Path $taskClient '.git'))) {
    if (Test-Path -LiteralPath $taskClient) { throw 'client directory already exists without git metadata; preserving it' }
    & git clone --depth 1 --branch v0.9.2 https://github.com/chen08209/FlClash.git $taskClient
    if ($LASTEXITCODE -ne 0) { throw 'Source checkout failed' }
    Push-Location $taskClient
    try {
        & git switch -c vpnn/foundation
        & git config submodule.core/Clash.Meta.url https://github.com/chen08209/Clash.Meta.git
        & git -c 'url.https://github.com/.insteadOf=git@github.com:' submodule update --init --recursive --depth 1
        if ($LASTEXITCODE -ne 0) { throw 'Core checkout failed' }
        Set-Content -LiteralPath 'rust-toolchain.toml' -Value @('[toolchain]','channel = "1.99.0"','profile = "minimal"') -Encoding ascii
    } finally {
        Pop-Location
    }
}
