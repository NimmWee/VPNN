. (Join-Path $PSScriptRoot 'env.ps1')
$taskEmulator = Join-Path $env:ANDROID_HOME 'emulator\emulator.exe'
& $taskEmulator -avd VPNN_API35 -no-audio -gpu swiftshader -memory 2048 -cores 2
