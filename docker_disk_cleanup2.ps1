$ErrorActionPreference = 'SilentlyContinue'
$keeper = 'D:\Docker\install\DockerDesktopInstaller.exe'
$freeBefore = [math]::Round((Get-PSDrive C).Free/1GB, 2)
Write-Output "C_FREE_GB_BEFORE=$freeBefore"

function Get-DirSizeBytes($path) {
  if (-not (Test-Path $path)) { return 0 }
  $sum = (Get-ChildItem $path -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  if (-not $sum) { return 0 }
  return [int64]$sum
}

$script:bytesFreed = [int64]0
$script:deleted = @()

function Remove-Target($path, $reason) {
  if (-not (Test-Path $path)) { return }
  if ($path -eq $keeper) { return }
  $b = Get-DirSizeBytes $path
  if ((Get-Item -LiteralPath $path -Force).PSIsContainer -eq $false) {
    $b = (Get-Item -LiteralPath $path -Force).Length
  }
  try {
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
    $script:bytesFreed += $b
    $script:deleted += [pscustomobject]@{ Path = $path; GB = [math]::Round($b/1GB, 3); Reason = $reason }
    Write-Output ("DELETED: {0} ({1:N2} GB) - {2}" -f $path, ($b/1GB), $reason)
  } catch {
    Write-Output ("FAILED: {0} - {1}" -f $path, $_.Exception.Message)
  }
}

Get-Process | Where-Object { $_.ProcessName -match 'DockerDesktopInstaller' } | ForEach-Object {
  Write-Output ("KILL PID {0}" -f $_.Id)
  Stop-Process -Id $_.Id -Force
}

$wingetBase = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
if (Test-Path $wingetBase) {
  Get-ChildItem $wingetBase -Directory | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
    Remove-Target $_.FullName 'WinGet Packages Docker cache'
  }
}

$wingetDl = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Downloads'
if (Test-Path $wingetDl) {
  Get-ChildItem $wingetDl -Force | Where-Object { $_.Name -match 'docker|Docker' } | ForEach-Object {
    Remove-Target $_.FullName 'WinGet Downloads'
  }
}

$tempWinGet = Join-Path $env:LOCALAPPDATA 'Temp\WinGet'
if (Test-Path $tempWinGet) {
  Get-ChildItem $tempWinGet -Force | Where-Object { $_.Name -match 'Docker|docker' } | ForEach-Object {
    Remove-Target $_.FullName 'Temp WinGet Docker extract'
  }
}

$temp = Join-Path $env:LOCALAPPDATA 'Temp'
Get-ChildItem $temp -Force | Where-Object { $_.Name -like '*docker*' -or $_.Name -like '*Docker*' } | ForEach-Object {
  Remove-Target $_.FullName 'Temp docker-named'
}

$dl = Join-Path $env:USERPROFILE 'Downloads'
Get-ChildItem $dl -Force | Where-Object { $_.Name -like '*Docker*' } | ForEach-Object {
  Remove-Target $_.FullName 'Downloads Docker'
}

$searchPaths = @($wingetBase, $wingetDl, $tempWinGet, $temp, $dl)
foreach ($sp in $searchPaths) {
  if (Test-Path $sp) {
    Get-ChildItem $sp -Filter 'DockerDesktopInstaller.exe' -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_.FullName -ne $keeper) { Remove-Target $_.FullName 'Duplicate installer' }
    }
  }
}

$freeAfter = [math]::Round((Get-PSDrive C).Free/1GB, 2)
Write-Output '=== DELETED LIST ==='
$script:deleted | ForEach-Object { Write-Output ("  {0} | {1} GB | {2}" -f $_.Path, $_.GB, $_.Reason) }
if ($script:deleted.Count -eq 0) { Write-Output '  (none)' }
Write-Output ("GB_FREED={0:N2}" -f ($script:bytesFreed/1GB))
Write-Output "C_FREE_GB_AFTER=$freeAfter"
Write-Output ("C_FREE_DELTA={0:N2}" -f ($freeAfter - $freeBefore))
if (Test-Path $keeper) {
  $k = Get-Item $keeper
  Write-Output ("KEEPER_OK=YES SIZE_GB={0:N3}" -f ($k.Length/1GB))
} else { Write-Output 'KEEPER_OK=NO' }
