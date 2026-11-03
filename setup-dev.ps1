# One-time setup of a FreePDF dev machine. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\setup-dev.ps1
# Needs: Python 3.13, Node.js, Rust (rustup), uv (optional, faster).
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $env:LOCALAPPDATA 'FreePDF-dev\venv'

Write-Host "Python engine venv -> $venv"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv --python 3.13 $venv
    uv pip install --python "$venv\Scripts\python.exe" -r "$root\engine\requirements.txt"
} else {
    py -3.13 -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install -r "$root\engine\requirements.txt"
}

Write-Host "App dependencies (npm)"
Push-Location "$root\app"
npm install
Pop-Location

Write-Host "Done. Start the app with:  cd app; npx tauri dev"
