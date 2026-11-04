. (Join-Path $PSScriptRoot 'env.ps1')
& flutter doctor -v
& flutter devices
if (Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'emulator\emulator.exe')) {
    & (Join-Path $env:ANDROID_HOME 'emulator\emulator.exe') -accel-check
}
