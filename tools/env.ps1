$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:VPNN_ROOT = $taskRoot
$env:FLUTTER_ROOT = Join-Path $taskRoot '.toolchains\flutter'
$env:ANDROID_HOME = Join-Path $taskRoot '.toolchains\android-sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:CARGO_HOME = Join-Path $taskRoot '.toolchains\cargo'
$env:RUSTUP_HOME = Join-Path $taskRoot '.toolchains\rustup'
$env:RUSTUP_TOOLCHAIN = '1.99.0'
$env:LIBCLANG_PATH = Join-Path $taskRoot '.toolchains\llvm\bin'
$env:PUB_CACHE = Join-Path $taskRoot '.cache\pub'
$env:GRADLE_USER_HOME = Join-Path $taskRoot '.cache\gradle'
$env:ANDROID_AVD_HOME = Join-Path $taskRoot '.android\avd'
$env:GOPATH = Join-Path $taskRoot '.cache\go'
$env:GOCACHE = Join-Path $taskRoot '.cache\go-build'
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
$env:DART_SUPPRESS_ANALYTICS = 'true'
$env:GODEBUG = 'http2client=0'
$env:CARGO_HTTP_MULTIPLEXING = 'false'
$env:JAVA_TOOL_OPTIONS = '-Djava.net.preferIPv4Stack=true -Djdk.tls.client.protocols=TLSv1.2 -Dsun.net.client.defaultConnectTimeout=15000 -Dsun.net.client.defaultReadTimeout=30000'
$taskJava = Get-ChildItem -LiteralPath (Join-Path $taskRoot '.toolchains\java') -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } | Select-Object -First 1
if ($taskJava) { $env:JAVA_HOME = $taskJava.FullName }
$taskPaths = @(
    (Join-Path $env:FLUTTER_ROOT 'bin'),
    (Join-Path $taskRoot '.toolchains\go\bin'),
    (Join-Path $env:CARGO_HOME 'bin'),
    (Join-Path $env:ANDROID_HOME 'cmdline-tools\latest\bin'),
    (Join-Path $env:ANDROID_HOME 'platform-tools'),
    (Join-Path $env:ANDROID_HOME 'emulator')
)
if ($env:JAVA_HOME) { $taskPaths += Join-Path $env:JAVA_HOME 'bin' }
$env:PATH = ($taskPaths -join ';') + ';' + $env:PATH
