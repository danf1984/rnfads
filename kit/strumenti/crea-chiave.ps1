# Crea la coppia di chiavi Ed25519 per firmare gli aggiornamenti (Windows, da fare UNA volta).
# Serve openssl: c'è in Git for Windows (C:\Program Files\Git\usr\bin\openssl.exe).
# Uso (PowerShell):  .\crea-chiave.ps1        -> cartella Documenti\rnfads-chiavi
$ErrorActionPreference = 'Stop'
$ossl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $ossl -and (Test-Path 'C:\Program Files\Git\usr\bin\openssl.exe')) { $ossl = 'C:\Program Files\Git\usr\bin\openssl.exe' }
if (-not $ossl) { throw "openssl non trovato: installa Git for Windows (https://git-scm.com) e riprova" }
$dir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'rnfads-chiavi'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$priv = Join-Path $dir 'aggiornamenti-privata.pem'; $pub = Join-Path $dir 'aggiornamenti-pubblica.pem'
if (Test-Path $priv) { throw "Esiste già $priv : non la sovrascrivo" }
& $ossl genpkey -algorithm ed25519 -out $priv
& $ossl pkey -in $priv -pubout -out $pub
Write-Host "Fatto."
Write-Host "  Privata (resta qui, NON nel kit): $priv"
Write-Host "  Pubblica (copiala in kit\chiavi\): $pub"
