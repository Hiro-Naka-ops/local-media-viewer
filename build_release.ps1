$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "Local-Media-Viewer" `
    --paths "src" `
    "run_viewer.pyw"

Write-Host "Release executable: dist\Local-Media-Viewer.exe"
