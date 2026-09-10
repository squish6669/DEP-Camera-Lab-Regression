[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$ReplayCsv,
    [string]$CameraRoll = "$env:USERPROFILE\OneDrive - Riverside County (RivCo.org)\Pictures\Camera Roll",
    [int]$TargetCount = 123,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step([string]$Text) { Write-Host "[Camera Lab] $Text" -ForegroundColor Cyan }
function Normalize-Name([string]$Name) { if ([string]::IsNullOrWhiteSpace($Name)) { return '' }; return [IO.Path]::GetFileName($Name.Trim()) }

$zipPath = Join-Path $RepoRoot 'Camera Roll.zip'
$gtPath  = Join-Path $RepoRoot 'data\Camera-Lab-Ground-Truth.csv'
$outRoot = Join-Path $RepoRoot 'Unified-Corpus-Build'
$imgOut  = Join-Path $outRoot 'Camera Roll'
$invPath = Join-Path $outRoot 'Unified-Corpus-Inventory.csv'
$outGt   = Join-Path $outRoot 'Camera-Lab-Ground-Truth.csv'
$outZip  = Join-Path $outRoot 'Camera Roll-123.zip'

if (-not (Test-Path $zipPath)) { throw "Missing existing corpus zip: $zipPath" }
if (-not (Test-Path $gtPath)) { throw "Missing ground truth: $gtPath" }
if (-not (Test-Path $CameraRoll)) { throw "Camera Roll not found: $CameraRoll" }

if (-not $ReplayCsv) {
    $searchRoots = @(
        (Join-Path $env:USERPROFILE 'Downloads'),
        (Join-Path $env:USERPROFILE 'Desktop'),
        $RepoRoot
    ) | Where-Object { Test-Path $_ }
    $candidate = Get-ChildItem -Path $searchRoots -Filter 'Unseen-Parser-Replay*.csv' -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($candidate) { $ReplayCsv = $candidate.FullName }
}

Write-Step "Preparing clean staging folder"
if (Test-Path $outRoot) { Remove-Item $outRoot -Recurse -Force }
New-Item -ItemType Directory -Path $imgOut -Force | Out-Null

Write-Step "Expanding existing corpus"
Expand-Archive -LiteralPath $zipPath -DestinationPath $imgOut -Force

# Flatten any nested directory from the source zip.
Get-ChildItem $imgOut -File -Recurse | ForEach-Object {
    if ($_.DirectoryName -ne $imgOut) {
        $dest = Join-Path $imgOut $_.Name
        if (-not (Test-Path $dest)) { Copy-Item $_.FullName $dest }
    }
}
Get-ChildItem $imgOut -Directory | Remove-Item -Recurse -Force

$existing = @{}
Get-ChildItem $imgOut -File | ForEach-Object { $existing[$_.Name.ToLowerInvariant()] = $_.FullName }
$initialCount = $existing.Count
Write-Step "Existing physical images: $initialCount"

$replayNames = New-Object System.Collections.Generic.HashSet[string] ([StringComparer]::OrdinalIgnoreCase)
if ($ReplayCsv -and (Test-Path $ReplayCsv)) {
    Write-Step "Reading replay: $ReplayCsv"
    foreach ($row in (Import-Csv -LiteralPath $ReplayCsv)) {
        foreach ($field in @('Image','ImagePath')) {
            if ($row.PSObject.Properties.Name -contains $field) {
                $n = Normalize-Name ([string]$row.$field)
                if ($n -match '\.(jpg|jpeg|png|bmp|tif|tiff)$') { [void]$replayNames.Add($n) }
            }
        }
    }
    Write-Step "Replay references: $($replayNames.Count) unique image names"
} else {
    Write-Warning 'No replay CSV found. The importer will still scan Camera Roll for exact existing/ground-truth filenames, but newer replay-only filenames cannot be targeted.'
}

$gt = @(Import-Csv -LiteralPath $gtPath)
$gtNames = New-Object System.Collections.Generic.HashSet[string] ([StringComparer]::OrdinalIgnoreCase)
foreach ($row in $gt) {
    $n = Normalize-Name ([string]$row.Image)
    if ($n) { [void]$gtNames.Add($n) }
}

$wanted = New-Object System.Collections.Generic.HashSet[string] ([StringComparer]::OrdinalIgnoreCase)
foreach ($n in $gtNames) { [void]$wanted.Add($n) }
foreach ($n in $replayNames) { [void]$wanted.Add($n) }

Write-Step "Indexing OneDrive Camera Roll"
$cameraIndex = @{}
Get-ChildItem -LiteralPath $CameraRoll -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -match '^\.(jpg|jpeg|png|bmp|tif|tiff)$' } |
    ForEach-Object {
        $key = $_.Name.ToLowerInvariant()
        if (-not $cameraIndex.ContainsKey($key)) { $cameraIndex[$key] = $_.FullName }
    }

$added = 0
foreach ($name in $wanted) {
    $key = $name.ToLowerInvariant()
    if (-not $existing.ContainsKey($key) -and $cameraIndex.ContainsKey($key)) {
        Copy-Item -LiteralPath $cameraIndex[$key] -Destination (Join-Path $imgOut $name) -Force
        $existing[$key] = Join-Path $imgOut $name
        $added++
    }
}
Write-Step "Recovered and added: $added"

# If replay references did not cover the full new set, preserve all explicitly dated Camera Lab images from Sep 8, 2026
# only when needed to reach target. This is intentionally conservative and does not invent identity ground truth.
if ($existing.Count -lt $TargetCount) {
    $dated = Get-ChildItem -LiteralPath $CameraRoll -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^WIN_20260908_.*\.(jpg|jpeg|png)$' } |
        Sort-Object Name
    foreach ($f in $dated) {
        if ($existing.Count -ge $TargetCount) { break }
        $key = $f.Name.ToLowerInvariant()
        if (-not $existing.ContainsKey($key)) {
            Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $imgOut $f.Name) -Force
            $existing[$key] = Join-Path $imgOut $f.Name
            $added++
        }
    }
}

$images = @(Get-ChildItem $imgOut -File | Sort-Object Name)
if ($images.Count -gt $TargetCount -and -not $Force) {
    throw "Recovered $($images.Count) images, which exceeds target $TargetCount. Re-run with -Force only after reviewing the inventory."
}

# Build output ground truth. Existing verified rows are preserved exactly; new images get blank expected values and Verified=NO.
$gtByName = @{}
foreach ($row in $gt) { $gtByName[(Normalize-Name ([string]$row.Image)).ToLowerInvariant()] = $row }
$newGt = New-Object System.Collections.Generic.List[object]
$inventory = New-Object System.Collections.Generic.List[object]

foreach ($img in $images) {
    $key = $img.Name.ToLowerInvariant()
    if ($gtByName.ContainsKey($key)) {
        $row = $gtByName[$key]
        $newGt.Add($row)
        $verified = [string]$row.Verified
        $source = 'existing-ground-truth'
    } else {
        $row = [pscustomobject]@{
            Image = $img.Name
            ExpectedDriveType = ''
            ExpectedManufacturer = ''
            ExpectedModel = ''
            ExpectedSerial = ''
            ExpectedCapacity = ''
            ExpectedCT = ''
            Verified = 'NO'
            VerificationNotes = 'Recovered source image; ground truth intentionally blank pending visual verification.'
        }
        $newGt.Add($row)
        $verified = 'NO'
        $source = 'recovered-camera-roll'
    }
    $inventory.Add([pscustomobject]@{
        Image = $img.Name
        Bytes = $img.Length
        GroundTruthVerified = $verified
        Source = $source
    })
}

$newGt | Export-Csv -LiteralPath $outGt -NoTypeInformation -Encoding UTF8
$inventory | Export-Csv -LiteralPath $invPath -NoTypeInformation -Encoding UTF8

if (Test-Path $outZip) { Remove-Item $outZip -Force }
Compress-Archive -Path (Join-Path $imgOut '*') -DestinationPath $outZip -CompressionLevel Optimal

$status = if ($images.Count -eq $TargetCount) { 'COMPLETE' } else { 'INCOMPLETE' }
Write-Host ''
Write-Host "Unified Camera Lab corpus: $status" -ForegroundColor $(if ($status -eq 'COMPLETE') { 'Green' } else { 'Yellow' })
Write-Host "  Existing images : $initialCount"
Write-Host "  Recovered added : $added"
Write-Host "  Final images     : $($images.Count) / $TargetCount"
Write-Host "  Verified GT rows : $(@($newGt | Where-Object { $_.Verified -match '^(YES|TRUE|1)$' }).Count)"
Write-Host "  Corpus zip       : $outZip"
Write-Host "  Ground truth     : $outGt"
Write-Host "  Inventory        : $invPath"

if ($images.Count -ne $TargetCount) {
    exit 2
}
