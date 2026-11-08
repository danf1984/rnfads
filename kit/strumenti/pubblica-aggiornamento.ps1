# Pubblica un aggiornamento sul canale online (Windows, cartella del sito GitHub Pages).
# Uso:
#   .\pubblica-aggiornamento.ps1 -Deb .\rnfads_1.1+202611151200_all.deb -Canale stable -Sito C:\Users\TU\Documents\GitHub\rnfads-aggiornamenti
#   (facoltativi: -Key percorso\aggiornamenti-privata.pem  -Novita percorso\novita.txt)
# Crea/aggiorna nel sito: pool\<pacchetto>.deb(.sig), <canale>.json(.sig), index.html
# Poi in GitHub Desktop: Commit + Push (oppure: git add -A; git commit -m "..."; git push)
param(
  [Parameter(Mandatory=$true)][string]$Deb,
  [Parameter(Mandatory=$true)][ValidateSet('stable','beta')][string]$Canale,
  [Parameter(Mandatory=$true)][string]$Sito,
  [string]$Key = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'rnfads-chiavi\aggiornamenti-privata.pem'),
  [string]$Novita = ''
)
$ErrorActionPreference = 'Stop'
$ossl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $ossl -and (Test-Path 'C:\Program Files\Git\usr\bin\openssl.exe')) { $ossl = 'C:\Program Files\Git\usr\bin\openssl.exe' }
if (-not $ossl) { throw "openssl non trovato: installa Git for Windows" }
if (-not (Test-Path $Key)) { throw "Chiave privata non trovata: $Key" }
$Deb = (Resolve-Path $Deb).Path
$name = Split-Path $Deb -Leaf
if ($name -notmatch '^[a-z0-9-]+_(.+)_all\.deb$') { throw "Nome del pacchetto non riconosciuto: $name" }
$pv = $Matches[1]
$ver = ($pv -split '\+')[0] -replace '~','-'
$pool = Join-Path $Sito 'pool'
New-Item -ItemType Directory -Force -Path $pool | Out-Null
$dst = Join-Path $pool $name
Copy-Item $Deb $dst -Force
& $ossl pkeyutl -sign -inkey $Key -rawin -in $dst -out "$dst.sig"
if ($LASTEXITCODE -ne 0) { throw "Firma del pacchetto non riuscita" }
$sha = (Get-FileHash $dst -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $dst).Length
$notes = ''
if ($Novita) { $notes = (Get-Content $Novita -Raw -Encoding UTF8).Trim() }
$m = [ordered]@{ name='RNFADS'; package='nido-nas'; channel=$Canale; version=$ver; package_version=$pv; deb=$name;
                 sha256=$sha; size=$size; notes=$notes; date=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
$json = ($m | ConvertTo-Json -Depth 3) -replace "`r`n", "`n"
$out = Join-Path $Sito "$Canale.json"
[IO.File]::WriteAllText($out, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
& $ossl pkeyutl -sign -inkey $Key -rawin -in $out -out "$out.sig"
if ($LASTEXITCODE -ne 0) { throw "Firma del manifesto non riuscita" }
$idx = Join-Path $Sito 'index.html'
if (-not (Test-Path $idx)) {
  [IO.File]::WriteAllText($idx, "<!doctype html><meta charset=`"utf-8`"><title>RNFADS updates</title><p>Canale degli aggiornamenti di RNFADS: <a href=`"stable.json`">stable</a> &middot; <a href=`"beta.json`">beta</a></p>`n", (New-Object System.Text.UTF8Encoding($false)))
}
$nj = Join-Path $Sito '.nojekyll'; if (-not (Test-Path $nj)) { New-Item -ItemType File -Path $nj | Out-Null }
Write-Host "Pubblicato $ver ($pv) sul canale $Canale in $Sito"
Write-Host "Ora in GitHub Desktop: Commit to main, poi Push origin."
