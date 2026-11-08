# Genera la ISO da Windows usando Docker Desktop.
# Uso: tasto destro sul file > "Esegui con PowerShell", oppure da PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\build-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

try { docker version | Out-Null }
catch {
    Write-Host "Docker non risponde: avvia Docker Desktop e riprova." -ForegroundColor Red
    Read-Host "Premi Invio per chiudere"
    exit 1
}

Write-Host "Avvio la build in un container Ubuntu (la prima volta ci vuole parecchio)..." -ForegroundColor Magenta

# La cartella di lavoro vive nel volume "nido-build" (file system Linux):
# la build non funziona su cartelle di Windows. La ISO finale arriva in .\out
docker run --rm --privileged `
  -v "${PWD}:/nido" `
  -v nido-build:/build `
  -e NIDO_WORK=/build/work `
  -e NIDO_CACHE=/build/cache `
  ubuntu:26.04 `
  bash -c "tr -d '\r' < /nido/build.sh > /tmp/build.sh && NIDO_ROOT=/nido bash /tmp/build.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nISO pronta nella cartella 'out'." -ForegroundColor Green
} else {
    Write-Host "`nLa build si e' fermata: guarda build.log." -ForegroundColor Red
}
Read-Host "Premi Invio per chiudere"
