param(
    [Parameter(Mandatory)][string]$LiveKit,
    [string]$Go = 'go',
    [ValidateRange(1024,65532)][int]$Port = 28760,
    [switch]$Race
)
$ErrorActionPreference = 'Stop'
$LiveKit = (Resolve-Path -LiteralPath $LiveKit).Path
$Go = (Get-Command $Go -CommandType Application).Source
$tcp = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
$tcp.ExclusiveAddressUse = $true
$udp = [Net.Sockets.UdpClient]::new()
$udp.ExclusiveAddressUse = $true
try {
    $tcp.Start()
    $udp.Client.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Any, ($Port + 2)))
} finally {
    $tcp.Stop()
    $udp.Dispose()
}

$run = Join-Path ([IO.Path]::GetTempPath()) ('vpnn-wb-p6-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
Write-Host "Lab logs: $run"
$config = Join-Path $run 'livekit.yaml'
$key = 'wb-lab'
$secret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
@"
port: $Port
bind_addresses: ['127.0.0.1']
rtc:
  udp_port: $($Port + 2)
  tcp_port: 0
  use_external_ip: false
  enable_loopback_candidate: true
  stun_servers: ['127.0.0.1:$($Port + 3)']
  interfaces:
    includes: ['Loopback Pseudo-Interface 1', 'lo']
keys:
  $($key): $secret
"@ | Set-Content -LiteralPath $config -Encoding ascii
$saved = @{}
$server = $null
Push-Location $PSScriptRoot
try {
    $argsForServer = '--config "{0}" --node-ip 127.0.0.1' -f $config
    $server = Start-Process -FilePath $LiveKit -ArgumentList $argsForServer `
        -RedirectStandardOutput (Join-Path $run 'sfu.out.log') `
        -RedirectStandardError (Join-Path $run 'sfu.err.log') -WindowStyle Hidden -PassThru
    $endpoint = "http://127.0.0.1:$Port"
    $healthy = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($server.HasExited) { throw "LiveKit exited with code $($server.ExitCode). See $run" }
        try {
            $response = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (!$healthy) { throw "LiveKit did not start. See $run" }
    foreach ($entry in @{ WB_LAB_URL = $endpoint; WB_LAB_KEY = $key; WB_LAB_SECRET = $secret }.GetEnumerator()) {
        $saved[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key)
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
    $flags = @()
    if ($Race) { $flags += '-race' }
    & $Go test @flags -v -count=1 -timeout=45s ./... | Tee-Object -FilePath (Join-Path $run 'test.log')
    if ($LASTEXITCODE -ne 0) { throw "Lab tests failed. See $run" }
} finally {
    foreach ($entry in $saved.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
    if ($server -and !$server.HasExited) {
        $server.Kill()
        if (!$server.WaitForExit(5000)) { throw "Lab LiveKit did not exit. See $run" }
    }
    Remove-Item -LiteralPath $config
    Pop-Location
}
