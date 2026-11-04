param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).ProviderPath.TrimEnd('\')
$taskArtifacts = Join-Path $taskRoot 'artifacts'
$taskProtected = @((Join-Path $taskRoot 'private'), (Join-Path $taskRoot '.toolchains'))
foreach ($taskManifest in @(Get-Item -LiteralPath (Join-Path $taskArtifacts 'LATEST.json')) + @(Get-ChildItem -LiteralPath $taskArtifacts -Filter 'CANDIDATE-*.json' -File)) {
    $taskData = Get-Content -LiteralPath $taskManifest.FullName -Raw | ConvertFrom-Json
    $taskProtected += [IO.Path]::GetFullPath((Join-Path $taskArtifacts $taskData.windowsDirectory))
    foreach ($taskName in $taskData.files.PSObject.Properties.Name) {
        $taskProtected += [IO.Path]::GetFullPath((Join-Path $taskArtifacts $taskName))
    }
}
$taskTargets = @('downloads', '.cache\go-build', '.cache\gradle\caches\9.8.0\transforms', 'client\build', 'client\.dart_tool\flutter_build', 'client\.dart_tool\hooks_runner', '.android\avd\VPNN_API35.avd\snapshots')
$taskOldDirectories = @('windows-0.1.1', 'windows-0.1.1-final', 'windows-0.1.1-rc2', 'windows-production-candidate', 'windows-release', 'windows-transport-test', 'windows-transport-test-v2')
foreach ($taskName in $taskOldDirectories) { $taskTargets += 'artifacts\' + $taskName }
$taskOldFiles = @('foundation-android-x64-debug.apk', 'VPNN-Android-arm64-test.apk', 'VPNN-Android-armv7-test.apk', 'vpnn-android-x64-transport-test.apk', 'VPNN-Windows-DNS-VK-test.zip', 'VPNN-Windows-DNS-VK-test-v2.zip', 'VPNN-Windows-Release-Candidate.zip', 'VPNN-Windows.zip', 'LATEST-0.1.1.json', 'SHA256SUMS-0.1.1.txt')
foreach ($taskName in $taskOldFiles) { $taskTargets += 'artifacts\' + $taskName }
foreach ($taskFile in Get-ChildItem -LiteralPath $taskArtifacts -File) {
    if ($taskFile.Name -match '^VPNN-(Windows|Sources)-0\.1\.1\.zip$|^VPNN-Android-(arm64|armv7|x64)-0\.1\.1\.apk$') {
        $taskTargets += 'artifacts\' + $taskFile.Name
    }
}
$taskRunning = @(Get-Process | ForEach-Object { try { if ($_.Path) { $_.Path } } catch {} })
$taskPlan = @()
$taskSkipped = @()
foreach ($taskRelative in $taskTargets) {
	if ($taskRelative.StartsWith('.cache\gradle\') -and @($taskRunning | Where-Object { $_.StartsWith((Join-Path $taskRoot '.toolchains\java') + '\', [StringComparison]::OrdinalIgnoreCase) }).Count) { $taskSkipped += [pscustomobject]@{ path = $taskRelative; reason = 'workspace Java is active' }; continue }
	if ($taskRelative -eq '.android\avd\VPNN_API35.avd\snapshots' -and @($taskRunning | Where-Object { $_.StartsWith((Join-Path $taskRoot '.toolchains\android-sdk\emulator') + '\', [StringComparison]::OrdinalIgnoreCase) }).Count) {
		throw 'An emulator is active; snapshot cleanup refused'
	}
    $taskPath = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskRelative))
    if (-not $taskPath.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup target escapes workspace' }
    if (-not (Test-Path -LiteralPath $taskPath)) { continue }
    $taskResolved = (Resolve-Path -LiteralPath $taskPath).ProviderPath.TrimEnd('\')
    if ($taskResolved -ne $taskPath) { throw 'Cleanup target resolution changed' }
    foreach ($taskKeep in $taskProtected) {
        if ($taskPath -eq $taskKeep -or $taskPath.StartsWith($taskKeep + '\', [StringComparison]::OrdinalIgnoreCase) -or $taskKeep.StartsWith($taskPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw ('Protected release or recovery target: ' + $taskRelative)
        }
    }
    if (@($taskRunning | Where-Object { $_ -eq $taskPath -or $_.StartsWith($taskPath + '\', [StringComparison]::OrdinalIgnoreCase) }).Count) { $taskSkipped += [pscustomobject]@{ path = $taskRelative; reason = 'executable is running' }; continue }
    $taskItem = Get-Item -LiteralPath $taskPath -Force
    if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Reparse-point cleanup target: ' + $taskRelative) }
    if ($taskItem.PSIsContainer -and @(Get-ChildItem -LiteralPath $taskPath -Directory -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw ('Nested reparse point: ' + $taskRelative)
    }
    $taskBytes = if ($taskItem.PSIsContainer) { [long](Get-ChildItem -LiteralPath $taskPath -File -Recurse -Force | Measure-Object -Property Length -Sum).Sum } else { $taskItem.Length }
    $taskPlan += [pscustomobject]@{ path = $taskRelative; absolutePath = $taskPath; bytes = $taskBytes }
}
$taskFreeBefore = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskRoot)).AvailableFreeSpace
$taskResults = @()
foreach ($taskEntry in $taskPlan) {
    $taskRemoved = $false
    $taskError = $null
    if ($Apply) {
        try { Remove-Item -LiteralPath $taskEntry.absolutePath -Recurse -Force; $taskRemoved = -not (Test-Path -LiteralPath $taskEntry.absolutePath) }
        catch { $taskError = $_.Exception.Message }
    }
    $taskResults += [pscustomobject]@{ path = $taskEntry.path; bytesBefore = $taskEntry.bytes; removed = $taskRemoved; error = $taskError }
}
$taskFreeAfter = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskRoot)).AvailableFreeSpace
$taskReport = [ordered]@{ applied = [bool]$Apply; entries = $taskResults; skipped = $taskSkipped; plannedBytes = [long]($taskPlan | Measure-Object -Property bytes -Sum).Sum; diskFreeDeltaBytes = $taskFreeAfter - $taskFreeBefore }
$taskOutput = Join-Path $taskRoot $(if ($Apply) { 'logs\compact-workspace-result.json' } else { 'logs\compact-workspace-plan.json' })
$taskReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskOutput -Encoding utf8
[pscustomobject]@{ applied = [bool]$Apply; targets = $taskPlan.Count; plannedGiB = [math]::Round($taskReport.plannedBytes / 1GB, 2); diskFreeDeltaGiB = [math]::Round($taskReport.diskFreeDeltaBytes / 1GB, 2); failures = @($taskResults | Where-Object error).Count } | ConvertTo-Json
