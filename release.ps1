# Builds a signed installer and publishes it as a GitHub release, so installed copies update themselves.
#   powershell -ExecutionPolicy Bypass -File .\release.ps1 -Version 0.1.1 -Notes "What changed"
# Needs the signing key in %USERPROFILE%\.tauri (freepdf.key + freepdf.key.password). Never commit those files.
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "Bug fixes and improvements.",
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$app = Join-Path $root 'app'
$tauri = Join-Path $app 'src-tauri'
$repo = 'Mkhi1/freepdf'
$keyDir = Join-Path $env:USERPROFILE '.tauri'

if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must look like 1.2.3" }

function Set-Version([string]$path, [string]$pattern, [string]$replacement) {
    $text = [IO.File]::ReadAllText($path)
    $regex = [regex]$pattern
    if (-not $regex.IsMatch($text)) { throw "Could not find the version in $path" }
    [IO.File]::WriteAllText($path, $regex.Replace($text, $replacement, 1))
}

Write-Host "1/3 Version $Version"
Set-Version (Join-Path $tauri 'tauri.conf.json') '"version":\s*"[^"]+"' "`"version`": `"$Version`""
Set-Version (Join-Path $app 'package.json') '"version":\s*"[^"]+"' "`"version`": `"$Version`""
Set-Version (Join-Path $tauri 'Cargo.toml') '(?m)^version = "[^"]+"' "version = `"$Version`""

if (-not $SkipBuild) {
    Write-Host "2/3 Building the signed installer"
    $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -Raw (Join-Path $keyDir 'freepdf.key')
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = Get-Content -Raw (Join-Path $keyDir 'freepdf.key.password')
    Push-Location $app
    try { npx tauri build; if ($LASTEXITCODE) { throw "Build failed" } } finally { Pop-Location }
}

Write-Host "3/3 Publishing v$Version on GitHub"
$nsis = Join-Path $tauri 'target\release\bundle\nsis'
$built = Get-ChildItem $nsis -Filter "*_${Version}_x64-setup.exe" | Select-Object -First 1
if (-not $built) { throw "No installer for $Version in $nsis" }
$out = Join-Path $nsis 'upload'
New-Item -ItemType Directory -Force $out | Out-Null
# GitHub renames spaces in asset names, so upload under a name without them.
$setup = Join-Path $out "FreePDF_${Version}_x64-setup.exe"
Copy-Item -Force $built.FullName $setup
$signature = (Get-Content -Raw "$($built.FullName).sig").Trim()

$manifest = [ordered]@{
    version   = $Version
    notes     = $Notes
    pub_date  = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    platforms = [ordered]@{
        'windows-x86_64' = [ordered]@{
            signature = $signature
            url       = "https://github.com/$repo/releases/download/v$Version/FreePDF_${Version}_x64-setup.exe"
        }
    }
}
$latest = Join-Path $out 'latest.json'
[IO.File]::WriteAllText($latest, ($manifest | ConvertTo-Json -Depth 5))

gh release create "v$Version" $setup $latest --repo $repo --title "Free PDF $Version" --notes $Notes --latest
if ($LASTEXITCODE) { throw "Publishing failed" }
Write-Host "Done. Installed copies will offer v$Version the next time they start."
