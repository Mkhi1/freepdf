# One-time setup of a FreePDF dev machine. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\setup-dev.ps1
# Needs: Python 3.13, Node.js, Rust (rustup), GitHub CLI logged in (gh auth login). uv is optional.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dev  = Join-Path $env:LOCALAPPDATA 'FreePDF-dev'
$venv = Join-Path $dev 'venv'
New-Item -ItemType Directory -Force $dev | Out-Null

Write-Host "1/3 Python engine venv -> $venv"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv --python 3.13 $venv
    uv pip install --python "$venv\Scripts\python.exe" -r "$root\engine\requirements.txt"
} else {
    py -3.13 -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install -r "$root\engine\requirements.txt"
}

Write-Host "2/3 OCR + translation data (from the private GitHub release)"
$tmp = Join-Path $env:TEMP 'freepdf-res'
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $tmp | Out-Null
gh release download resources-v1 --repo Mkhi1/freepdf --dir $tmp
Expand-Archive -Force (Join-Path $tmp 'freepdf-resources.zip') $tmp
$argos = Join-Path $dev 'argos'
New-Item -ItemType Directory -Force $argos | Out-Null
Copy-Item -Recurse -Force (Join-Path $tmp 'tessdata') $dev
Copy-Item -Recurse -Force (Join-Path $tmp 'packages') $argos
Copy-Item -Recurse -Force (Join-Path $tmp 'data') $argos
Remove-Item -Recurse -Force $tmp

Write-Host "3/3 App dependencies (npm)"
Push-Location "$root\app"
npm install
Pop-Location

Write-Host "Done. Start the app with:  cd app; npx tauri dev"
