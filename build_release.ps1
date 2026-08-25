$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Local-Media-Viewer" `
    --paths "src" `
    --exclude-module "numpy" `
    "run_viewer.pyw"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Release executable: dist\Local-Media-Viewer.exe"
