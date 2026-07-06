$ErrorActionPreference = 'SilentlyContinue'
$script:bytesFreed = [int64]0
$script:deleted = @()

$freeBefore = [math]::Round((Get-PSDrive C).Free/1GB, 2)
Write-Output "C_FREE_GB_BEFORE=$freeBefore"

function Get-DirSizeBytes($path) {
  if (-not (Test-Path $path)) { return 0 }
  $sum = (Get-ChildItem $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
  if (-not $sum) { return 0 }
  return [int64]$sum
}

Write-Output '=== SCAN REPORT ==='

$wingetBase = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
Write-Output "-- WinGet *Docker* packages --"
if (Test-Path $wingetBase) {
  Get-ChildItem $wingetBase -Directory | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
    $b = Get-DirSizeBytes $_.FullName
    Write-Output ("  {0}  {1:N3} GB" -f $_.FullName, ($b/1GB))
  }
}

$wingetDl = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Downloads'
Write-Output "-- WinGet Downloads *docker* --"
if (Test-Path $wingetDl) {
  Get-ChildItem $wingetDl -Force | Where-Object { $_.Name -match 'docker|Docker' } | ForEach-Object {
    $b = if ($_.PSIsContainer) { Get-DirSizeBytes $_.FullName } else { $_.Length }
    Write-Output ("  {0}  {1:N3} GB" -f $_.FullName, ($b/1GB))
  }
}

$temp = Join-Path $env:LOCALAPPDATA 'Temp'
Write-Output "-- Temp *docker* --"
Get-ChildItem $temp -Force | Where-Object { $_.Name -like '*docker*' -or $_.Name -like '*Docker*' } | ForEach-Object {
  $b = if ($_.PSIsContainer) { Get-DirSizeBytes $_.FullName } else { $_.Length }
  Write-Output ("  {0}  {1:N3} GB" -f $_.FullName, ($b/1GB))
}

$dl = Join-Path $env:USERPROFILE 'Downloads'
Write-Output "-- Downloads *Docker* --"
Get-ChildItem $dl -Force | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
  $b = if ($_.PSIsContainer) { Get-DirSizeBytes $_.FullName } else { $_.Length }
  Write-Output ("  {0}  {1:N3} GB" -f $_.FullName, ($b/1GB))
}

$pf = 'C:\Program Files\Docker'
Write-Output "-- Program Files Docker --"
if (Test-Path $pf) {
  $cnt = @(Get-ChildItem $pf -Force).Count
  if ($cnt -eq 0) { Write-Output '  EMPTY' } else {
    Write-Output ("  {0}  {1:N3} GB  items={2}" -f $pf, ((Get-DirSizeBytes $pf)/1GB), $cnt)
  }
}

Write-Output "-- DockerDesktopInstaller.exe (limited search) --"
$searchPaths = @(
  $wingetBase,
  $wingetDl,
  $temp,
  $dl,
  (Join-Path $env:LOCALAPPDATA 'Docker'),
  'C:\ProgramData\Docker'
)
foreach ($sp in $searchPaths) {
  if (Test-Path $sp) {
    Get-ChildItem $sp -Filter 'DockerDesktopInstaller.exe' -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
      Write-Output ("  {0}  {1:N3} GB" -f $_.FullName, ($_.Length/1GB))
    }
  }
}

$keeper = 'D:\Docker\install\DockerDesktopInstaller.exe'
Write-Output "-- Keeper --"
if (Test-Path $keeper) {
  $kf = Get-Item $keeper
  Write-Output ("  KEEP {0}  {1:N3} GB" -f $kf.FullName, ($kf.Length/1GB))
} else { Write-Output '  KEEPER MISSING' }

Write-Output '=== KILL PROCESSES ==='
Get-Process | Where-Object { $_.ProcessName -match 'DockerDesktopInstaller|Docker Desktop Installer' } | ForEach-Object {
  Write-Output ("  Stopping PID {0} {1}" -f $_.Id, $_.ProcessName)
  Stop-Process -Id $_.Id -Force
}
if (-not (Get-Process | Where-Object { $_.ProcessName -match 'DockerDesktopInstaller' })) {
  Write-Output '  No DockerDesktopInstaller processes'
}

Write-Output '=== DELETE ==='

function Remove-Target($path, $reason) {
  if (-not (Test-Path $path)) { return }
  if ($path -eq $script:keeper) { Write-Output "  SKIP keeper: $path"; return }
  $item = Get-Item -LiteralPath $path -Force
  $b = if ($item.PSIsContainer) { Get-DirSizeBytes $path } else { $item.Length }
  try {
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
    $script:bytesFreed += $b
    $script:deleted += [pscustomobject]@{ Path = $path; GB = [math]::Round($b/1GB, 3); Reason = $reason }
    Write-Output ("  DELETED {0} ({1:N3} GB) - {2}" -f $path, ($b/1GB), $reason)
  } catch {
    Write-Output ("  FAILED {0} - {1}" -f $path, $_.Exception.Message)
  }
}

$script:keeper = $keeper

if (Test-Path $wingetBase) {
  Get-ChildItem $wingetBase -Directory | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
    Remove-Target $_.FullName 'WinGet Docker package cache'
  }
}

if (Test-Path $wingetDl) {
  Get-ChildItem $wingetDl -Force | Where-Object { $_.Name -match 'docker|Docker' } | ForEach-Object {
    Remove-Target $_.FullName 'WinGet download cache'
  }
}

Get-ChildItem $temp -Force | Where-Object { $_.Name -like '*docker*' -or $_.Name -like '*Docker*' } | ForEach-Object {
  Remove-Target $_.FullName 'Temp docker artifacts'
}

Get-ChildItem $dl -Force | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
  Remove-Target $_.FullName 'Downloads Docker duplicate'
}

foreach ($sp in $searchPaths) {
  if (Test-Path $sp) {
    Get-ChildItem $sp -Filter 'DockerDesktopInstaller.exe' -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_.FullName -ne $keeper) {
        Remove-Target $_.FullName 'Duplicate installer on C'
      }
    }
  }
}

Write-Output '=== SUMMARY ==='
foreach ($d in $script:deleted) {
  Write-Output ("  - {0} ({1} GB) - {2}" -f $d.Path, $d.GB, $d.Reason)
}
if ($script:deleted.Count -eq 0) { Write-Output '  (nothing deleted - no matching targets found)' }
$gbFreed = [math]::Round($script:bytesFreed/1GB, 2)
$freeAfter = [math]::Round((Get-PSDrive C).Free/1GB, 2)
Write-Output "GB_FREED_REPORTED=$gbFreed"
Write-Output "C_FREE_GB_AFTER=$freeAfter"
Write-Output "C_FREE_DELTA=$([math]::Round($freeAfter - $freeBefore, 2))"
if (Test-Path $keeper) { Write-Output 'KEEPER_OK=YES' } else { Write-Output 'KEEPER_OK=NO' }
