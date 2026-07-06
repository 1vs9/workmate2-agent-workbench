$paths = @(
  "$env:LOCALAPPDATA\Docker",
  "$env:APPDATA\Docker",
  "$env:APPDATA\Docker Desktop",
  'C:\ProgramData\Docker',
  'C:\ProgramData\DockerDesktop',
  "$env:LOCALAPPDATA\Docker Desktop",
  "$env:LOCALAPPDATA\Packages\Docker.DockerDesktop*",
  "$env:LOCALAPPDATA\Microsoft\WindowsApps\Docker*"
)
Write-Output '=== Docker App paths ==='
foreach ($p in $paths) {
  Get-Item $p -ErrorAction SilentlyContinue | ForEach-Object {
    $b = (Get-ChildItem $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    if (-not $b) { $b = 0 }
    Write-Output ("{0}  {1:N2} GB" -f $_.FullName, ($b/1GB))
  }
}

Write-Output '=== WinGet all packages with Docker in name ==='
$pkg = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
if (Test-Path $pkg) {
  Get-ChildItem $pkg -Directory | Where-Object { $_.Name -match 'Docker|docker' } | ForEach-Object {
    $b = (Get-ChildItem $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    Write-Output ("{0}  {1:N2} GB" -f $_.FullName, (($b)/1GB))
  }
}

Write-Output '=== Large files named *Docker* under LocalAppData (max 20) ==='
Get-ChildItem $env:LOCALAPPDATA -Recurse -Force -ErrorAction SilentlyContinue |
  Where-Object { -not $_.PSIsContainer -and $_.Name -match 'Docker|docker' -and $_.Length -gt 10MB } |
  Sort-Object Length -Descending | Select-Object -First 20 |
  ForEach-Object { Write-Output ("{0}  {1:N2} MB" -f $_.FullName, ($_.Length/1MB)) }

Write-Output '=== DockerDesktopInstaller anywhere on C (Users) ==='
Get-ChildItem 'C:\Users\aaaww' -Filter 'DockerDesktopInstaller.exe' -Recurse -Force -ErrorAction SilentlyContinue |
  ForEach-Object { Write-Output ("{0}  {1:N2} GB" -f $_.FullName, ($_.Length/1GB)) }

Write-Output '=== Temp large dirs (top 15 by size, docker/winget in path only) ==='
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Temp') -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  $b = (Get-ChildItem $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  if ($b -gt 50MB -and ($_.FullName -match 'docker|Docker|winget|WinGet|DockerDesktop')) {
    [pscustomobject]@{ Path = $_.FullName; GB = [math]::Round($b/1GB, 2) }
  }
} | Sort-Object GB -Descending | Select-Object -First 15 | ForEach-Object { Write-Output ("{0}  {1} GB" -f $_.Path, $_.GB) }

Write-Output '=== C free ==='
Write-Output ("C_FREE_GB={0:N2}" -f ((Get-PSDrive C).Free/1GB))
Write-Output '=== D free ==='
Write-Output ("D_FREE_GB={0:N2}" -f ((Get-PSDrive D).Free/1GB))
