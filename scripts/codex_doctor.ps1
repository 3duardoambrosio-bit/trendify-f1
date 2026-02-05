param([switch]$Ping)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Ok($m){ Write-Host ("OK: " + $m) }
function Fail([int]$c,[string]$m){ Write-Host ("FAIL: " + $m); exit $c }

"ROOT={0}" -f (Get-Location).Path
"PS_VERSION={0}" -f $PSVersionTable.PSVersion.ToString()

# Binarios
$node  = Get-Command node  -ErrorAction SilentlyContinue
$npm   = Get-Command npm   -ErrorAction SilentlyContinue
$codex = Get-Command codex -ErrorAction SilentlyContinue

"NODE_PRESENT={0}"  -f [bool]$node
"NPM_PRESENT={0}"   -f [bool]$npm
"CODEX_PRESENT={0}" -f [bool]$codex

if ($node) { "NODE_VERSION={0}" -f (& node -v) }
if ($npm)  { "NPM_VERSION={0}"  -f (& npm -v) }

if (-not $codex) { Fail 10 "codex no está en PATH. Instala: npm i -g @openai/codex" }

$ver = & codex --version 2>&1
if ($LASTEXITCODE -ne 0) { Fail 11 "codex --version falló: $ver" }
"CODEX_VERSION={0}" -f $ver

& codex --help > $null
if ($LASTEXITCODE -ne 0) { Fail 12 "codex --help falló" }
Ok "codex ejecuta (help/version)"

# Paths deterministas (CODEX_HOME > default ~/.codex)
$codexHome = $env:CODEX_HOME
if (-not $codexHome) { $codexHome = (Join-Path $env:USERPROFILE ".codex") }

$cfg  = Join-Path $codexHome "config.toml"
$auth = Join-Path $codexHome "auth.json"

"CODEX_HOME={0}"        -f $codexHome
"CODEX_CONFIG_PATH={0}" -f $cfg
"CODEX_AUTH_PATH={0}"   -f $auth
"CONFIG_EXISTS={0}"     -f (Test-Path $cfg)
"AUTH_EXISTS={0}"       -f (Test-Path $auth)
"ENV_CODEX_API_KEY_SET={0}" -f [bool]$env:CODEX_API_KEY

# Parse store si existe config.toml (auto/file/keyring)
$store = "auto"
if (Test-Path $cfg) {
  $raw = Get-Content $cfg -Raw
  $m = [regex]::Match($raw,'cli_auth_credentials_store\s*=\s*"(auto|file|keyring)"')
  if ($m.Success) { $store = $m.Groups[1].Value }
}
"CRED_STORE={0}" -f $store

# Auth determinista:
# - Si hay CODEX_API_KEY => OK
# - Si store=file (o auto) => exigir auth.json > 20 bytes
# - Si store=keyring => no se puede inspeccionar; exige -Ping para probar
$authOk = $false
$signal = "none"

if ($env:CODEX_API_KEY) {
  $authOk = $true
  $signal = "env:CODEX_API_KEY"
} elseif ($store -in @("auto","file")) {
  if (Test-Path $auth) {
    $len = (Get-Item $auth).Length
    "AUTH_JSON_BYTES={0}" -f $len
    if ($len -gt 20) { $authOk = $true; $signal = "auth.json" }
  }
} elseif ($store -eq "keyring") {
  $signal = "keyring:needs_ping"
}

"AUTH_SIGNAL={0}" -f $signal
"AUTH_OK={0}"     -f $authOk

if (-not $authOk -and $store -in @("auto","file")) {
  Fail 20 "No hay auth file. Ejecuta: codex login --device-auth  (o define CODEX_API_KEY)."
}

if ($Ping) {
  # Ping real = obliga a que la sesión exista (si no, aquí truena y te enteras)
  $out = & codex --version 2>&1
  if ($LASTEXITCODE -ne 0) { Fail 30 "Ping falló (codex no responde estable)" }
  Ok "PING_OK (CLI responde; auth depende del store)"
}

Ok "CODEX_DOCTOR_PASS"
exit 0
