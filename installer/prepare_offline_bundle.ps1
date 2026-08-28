param(
  [string]$OutputZip = "LBPM-portable-offline-installer.zip",
  [switch]$NoDownload
)

$ErrorActionPreference = "Stop"
$BuilderVersion = "2.0.7"
$OpenMpiVersion = "4.1.8"
$ZlibVersion = "1.3.2"
$Hdf5Version = "1.14.6"
$LbpmCommit = "6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
$PatchSetId = "outletlayersphase-fix-v1"
$PatchFile = "0001-fix-OutletLayersPhase.patch"
$PatchShaExpected = "fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"
$Sources = Join-Path $PSScriptRoot "sources"
$Patches = Join-Path $PSScriptRoot "patches"
New-Item -ItemType Directory -Force -Path $Sources | Out-Null

$items = @(
  @{
    Name = "openmpi-$OpenMpiVersion.tar.gz"
    Urls = @("https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-$OpenMpiVersion.tar.gz")
    Sha  = "fb41086bbed9300baa2f3d7572491facfe5257412fa524ec5a396aa9101d5c62"
  },
  @{
    Name = "zlib-$ZlibVersion.tar.gz"
    Urls = @("https://www.zlib.net/zlib-$ZlibVersion.tar.gz", "https://www.zlib.net/fossils/zlib-$ZlibVersion.tar.gz")
    Sha = "bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16"
  },
  @{
    Name = "hdf5-$Hdf5Version.tar.gz"
    Urls = @(
      "https://support.hdfgroup.org/releases/hdf5/v1_14/v1_14_6/downloads/hdf5-$Hdf5Version.tar.gz",
      "https://github.com/HDFGroup/hdf5/releases/download/hdf5_$Hdf5Version/hdf5-$Hdf5Version.tar.gz"
    )
    Sha = "e4defbac30f50d64e1556374aa49e574417c9e72c6b1de7a4ff88c4b1bea6e9b"
  },
  @{
    Name = "LBPM-$LbpmCommit.tar.gz"
    Urls = @("https://github.com/OPM/LBPM/archive/$LbpmCommit.tar.gz", "https://codeload.github.com/OPM/LBPM/tar.gz/$LbpmCommit")
    Sha = $null
  }
)

function Get-Sha256([string]$Path) { return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant() }

function Download-Source($Item, [string]$Destination) {
  if ($NoDownload) { throw "Missing $($Item.Name). -NoDownload was requested. Put the file in sources/ first." }
  $lastError = $null
  foreach ($url in $Item.Urls) {
    Write-Host "Downloading $($Item.Name)"
    Write-Host "  from: $url"
    $part = "$Destination.part"
    Remove-Item -Force -ErrorAction SilentlyContinue $part
    try {
      if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fL --retry 5 --connect-timeout 20 -o $part $url
        if ($LASTEXITCODE -ne 0) { throw "curl.exe exited with $LASTEXITCODE" }
      } else {
        Invoke-WebRequest -Uri $url -OutFile $part -MaximumRedirection 10
      }
      Move-Item -Force $part $Destination
      return
    } catch {
      $lastError = $_
      Remove-Item -Force -ErrorAction SilentlyContinue $part
      Write-Warning "Download failed from $url"
    }
  }
  throw "Unable to download $($Item.Name). Last error: $lastError"
}

$patchPath = Join-Path $Patches $PatchFile
if (-not (Test-Path $patchPath)) { throw "Missing audited patch: $patchPath" }
$patchHash = Get-Sha256 $patchPath
if ($patchHash -ne $PatchShaExpected) { throw "Patch SHA256 mismatch. Expected $PatchShaExpected, got $patchHash" }
Write-Host "SHA256 OK: patches/$PatchFile = $patchHash"

foreach ($item in $items) {
  $dest = Join-Path $Sources $item.Name
  if (-not (Test-Path $dest)) { Download-Source $item $dest } else { Write-Host "Using existing $($item.Name)" }
  $hash = Get-Sha256 $dest
  if ($item.Sha -and $hash -ne $item.Sha) { throw "SHA256 mismatch for $($item.Name). Expected $($item.Sha), got $hash" }
  Write-Host "SHA256 OK: $($item.Name) = $hash"
}

$sumLines = foreach ($item in $items) { $dest = Join-Path $Sources $item.Name; "$(Get-Sha256 $dest)  $($item.Name)" }
$sumLines | Set-Content -Encoding ascii (Join-Path $Sources "SHA256SUMS")
"$patchHash  $PatchFile" | Set-Content -Encoding ascii (Join-Path $Patches "SHA256SUMS")

$manifest = @(
  "BUNDLE_FORMAT=2",
  "BUILDER_VERSION=$BuilderVersion",
  "LBPM_REPO=OPM/LBPM",
  "LBPM_COMMIT=$LbpmCommit",
  "LBPM_LOCAL_PATCHSET=$PatchSetId",
  "LBPM_LOCAL_PATCH=$PatchFile",
  "LBPM_LOCAL_PATCH_SHA256=$patchHash",
  "OPENMPI_VERSION=$OpenMpiVersion",
  "ZLIB_VERSION=$ZlibVersion",
  "HDF5_VERSION=$Hdf5Version",
  "CREATED_AT=$(Get-Date -Format o)"
)
$manifestPath = Join-Path $Sources "BUNDLE_MANIFEST.txt"
$manifestText = ($manifest -join "`n") + "`n"
[IO.File]::WriteAllText($manifestPath, $manifestText, [Text.Encoding]::ASCII)

$zipPath = if ([IO.Path]::IsPathRooted($OutputZip)) { $OutputZip } else { Join-Path (Split-Path $PSScriptRoot -Parent) $OutputZip }
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Write-Host "Creating final offline bundle: $zipPath"
Compress-Archive -Path $PSScriptRoot -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host ""
Write-Host "[OK] LBPM v$BuilderVersion offline bundle created: $zipPath"
Write-Host "Contains frozen upstream sources + audited OutletLayersPhase patch + Piston smoke installer."
