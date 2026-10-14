param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$inventory = Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'inspection/cleanup_inventory.csv')
$tracked = @(git -C $projectRoot ls-files)
$verified = @()
foreach ($candidate in $inventory) {
    if ($candidate.action -ne 'REMOVE_CACHE') { continue }
    $target = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $candidate.path))
    if (-not $target.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cache target escapes project root.' }
    if ($tracked -contains $candidate.path) { throw 'Tracked cache must be retained.' }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { continue }
    $item = Get-Item -LiteralPath $target -Force
    $ancestor = $item
    while ($ancestor -and $ancestor.FullName -ne $projectRoot) {
        if ($ancestor.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Do not traverse a cache reparse point.' }
        if ($ancestor -is [System.IO.FileInfo]) { $ancestor = $ancestor.Directory } else { $ancestor = $ancestor.Parent }
    }
    if ($candidate.path -match '/__pycache__/[^/]+\.pyc$') {
        $bytes = [System.IO.File]::ReadAllBytes($target)
        if ($bytes.Length -lt 16 -or $bytes[2] -ne 13 -or $bytes[3] -ne 10) { throw 'Unrecognized bytecode; retain for review.' }
        $sourceName = ($item.Name -split '\.')[0] + '.py'
        $sourcePath = Join-Path $item.Directory.Parent.FullName $sourceName
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw 'Source absent; retain bytecode.' }
    } elseif ($candidate.path -eq 'backend/.pytest_cache/.gitignore') {
        if ((Get-Content -LiteralPath $target -Raw).Replace("`r", '').Trim() -ne "# Created by pytest automatically.`n*") { throw 'Nonstandard cache ignore file; retain.' }
    } elseif ($candidate.path -eq 'backend/.pytest_cache/CACHEDIR.TAG') {
        if (-not (Get-Content -LiteralPath $target -Raw).StartsWith('Signature: 8a477f597d28d172789f06886806bc55')) { throw 'Nonstandard cache tag; retain.' }
    } elseif ($candidate.path -eq 'backend/.pytest_cache/README.md') {
        if (-not (Get-Content -LiteralPath $target -Raw).StartsWith('# pytest cache directory #')) { throw 'Nonstandard cache readme; retain.' }
    } elseif ($candidate.path -in @('backend/.pytest_cache/v/cache/lastfailed', 'backend/.pytest_cache/v/cache/nodeids')) {
        $null = Get-Content -LiteralPath $target -Raw | ConvertFrom-Json
    } else { throw 'Unrecognized generated cache candidate; retain.' }
    $verified += [pscustomobject]@{ path = $candidate.path; bytes = $item.Length; sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower(); target = $target }
}
if (-not $Apply) { $verified | Select-Object path,bytes; return }
$logPath = Join-Path $projectRoot 'verification/architecture-audit-2026-10-11/cache-removal.json'
if (Test-Path -LiteralPath $logPath) { throw 'Cleanup already recorded; do not overwrite.' }
$verified | Select-Object path,bytes,sha256 | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $logPath -Encoding UTF8
foreach ($candidate in $verified) { Remove-Item -LiteralPath $candidate.target -Force }
Write-Output "Removed $($verified.Count) validated cache files. No recursive directory deletion."
