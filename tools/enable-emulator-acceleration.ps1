$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskResult = Join-Path $taskRoot 'logs\hypervisor-platform.json'
try {
    $taskFeature = Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform
    if ($taskFeature.State -eq 'Enabled') {
        @{Feature='HypervisorPlatform';State='Enabled';RestartNeeded=$false} | ConvertTo-Json | Set-Content -LiteralPath $taskResult -Encoding utf8
    } else {
        $taskEnabled = Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All -NoRestart
        @{Feature='HypervisorPlatform';State='Enabled';RestartNeeded=[bool]$taskEnabled.RestartNeeded} | ConvertTo-Json | Set-Content -LiteralPath $taskResult -Encoding utf8
    }
} catch {
    @{Feature='HypervisorPlatform';Error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $taskResult -Encoding utf8
    exit 1
}
