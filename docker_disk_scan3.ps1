$tempWinGet = Join-Path $env:LOCALAPPDATA 'Temp\WinGet'
Write-Output "=== Contents of $tempWinGet ==="
if (Test-Path $tempWinGet) {
  Get-ChildItem $tempWinGet -Force -Recurse -ErrorAction SilentlyContinue | 
    Where-Object { -not $_.PSIsContainer } |
    Sort-Object Length -Descending | Select-Object -First 30 |
    ForEach-Object { Write-Output ("{0}  {1:N1} MB" -f $_.FullName, ($_.Length/1MB)) }
  $total = (Get-ChildItem $tempWinGet -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  Write-Output ("TOTAL_GB={0:N2}" -f ($total/1GB))
}

$wingetPaths = @(
  (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet'),
  (Join-Path $env:LOCALAPPDATA 'Temp\WinGet'),
  (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.DesktopAppInstaller*')
)
Write-Output '=== WinGet-related folder sizes ==='
foreach ($base in $wingetPaths) {
  Get-Item $base -ErrorAction SilentlyContinue | ForEach-Object {
    $b = (Get-ChildItem $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    Write-Output ("{0}  {1:N2} GB" -f $_.FullName, (($b)/1GB))
  }
}

Write-Output '=== Search DockerDesktop* files in Temp ==='
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Temp') -Recurse -Force -ErrorAction SilentlyContinue |
  Where-Object { -not $_.PSIsContainer -and $_.Name -match 'Docker|docker' } |
  ForEach-Object { Write-Output ("{0}  {1:N1} MB" -f $_.FullName, ($_.Length/1MB)) }
