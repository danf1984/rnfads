# Firma un pacchetto di aggiornamento (Windows): crea <pacchetto>.deb.sig accanto al .deb.
# Uso:  .\firma-pacchetto.ps1 .\rnfads_0.3~beta1+202611011200_all.deb
param([Parameter(Mandatory=$true)][string]$Deb, [string]$Key = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'rnfads-chiavi\aggiornamenti-privata.pem'))
$ErrorActionPreference = 'Stop'
$ossl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $ossl -and (Test-Path 'C:\Program Files\Git\usr\bin\openssl.exe')) { $ossl = 'C:\Program Files\Git\usr\bin\openssl.exe' }
if (-not $ossl) { throw "openssl non trovato: installa Git for Windows" }
& $ossl pkeyutl -sign -inkey $Key -rawin -in $Deb -out "$Deb.sig"
Write-Host "Firma creata: $Deb.sig (carica sul NAS il .deb e il .sig insieme)"
