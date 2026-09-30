param([string]$ClientRoot = 'C:\Games\Tanki')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$clientPath = [IO.Path]::GetFullPath($ClientRoot)
[xml]$clientVersion = Get-Content -LiteralPath (Join-Path $clientPath 'version.xml')
$versionMatch = [regex]::Match([string]$clientVersion.'version.xml'.version, '\d+\.\d+\.\d+\.\d+')
if(-not $versionMatch.Success) { throw 'Cannot determine client version' }
$version = $versionMatch.Value
if($version -ne '1.45.0.0') { throw "Client API was verified for 1.45.0.0, found $version" }
$running = @(Get-Process -Name 'Tanki' -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($clientPath + '\', [StringComparison]::OrdinalIgnoreCase) })
if($running.Count) { throw 'Close this client before installing' }
[xml]$meta = Get-Content -LiteralPath (Join-Path $projectRoot 'source\meta.xml')
if($meta.root.id -ne 'nidin.onslaught_recon_bounds') { throw 'Wrong mod id' }
$packageName = "$($meta.root.id)_$($meta.root.version).mtmod"
$source = Join-Path $projectRoot "dist\$packageName"
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$targetDir = Join-Path $clientPath "mods\$version"
if(-not (Test-Path -LiteralPath $targetDir -PathType Container)) { throw 'Active mods directory is absent' }
$previous = @(Get-ChildItem -LiteralPath $targetDir -File -Filter 'nidin.onslaught_recon*.mtmod' | Where-Object { $_.Name -match '^nidin\.onslaught_recon(?:_bounds)?_\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?\.mtmod$' })
if($previous.Count) {
    $backup = Join-Path $projectRoot ('build-artifacts\backups\' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach($file in $previous) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $backup $file.Name)
        if((Get-FileHash -LiteralPath (Join-Path $backup $file.Name)).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) { throw 'Backup hash mismatch' }
    }
    foreach($file in $previous) { Remove-Item -LiteralPath $file.FullName }
    Write-Output "Backup $backup"
}
$target = Join-Path $targetDir $packageName
Copy-Item -LiteralPath $source -Destination $target
if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) { throw 'Installed hash mismatch' }
$installed = @(Get-ChildItem -LiteralPath $targetDir -File -Filter 'nidin.onslaught_recon*.mtmod' | Where-Object { $_.Name -match '^nidin\.onslaught_recon(?:_bounds)?_\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?\.mtmod$' })
if($installed.Count -ne 1 -or $installed[0].Name -ne $packageName) { throw 'Duplicate mod packages after installation' }
Write-Output "Installed $target"
Write-Output "SHA256 $sourceHash"
