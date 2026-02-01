<#  OMEGA_control_tower.ps1
    PRE-SHOPIFY HARDENING (sin gastar, sin APIs):
      - asegura que OMEGA_ship_batch ya generó FINAL + IMPORT_KIT (si no, lo corre)
      - lint del CSV (handles, duplicados, precios numéricos si existen, CSV injection)
      - audit de URLs (HEAD 200) EN PARALELO (runspaces) + reporte CSV
      - genera manifest.json (hash, counts, duplicados, etc.)
      - crea ZIP del IMPORT_KIT listo para subir cuando ya pagues Shopify

    USO:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\OMEGA_control_tower.ps1 -Batch "9c6d555524d0"
      powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\OMEGA_control_tower.ps1 -Batch "9c6d..." -Reship -BaseMode auto -Concurrency 24 -TimeoutMs 15000
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$Batch,

  [ValidateSet("raw","cdn","auto")]
  [string]$BaseMode = "auto",

  [int]$TimeoutMs = 15000,
  [int]$Concurrency = 24,

  [switch]$Reship,          # fuerza re-correr OMEGA_ship_batch
  [switch]$SkipUrlAudit,    # si solo quieres lint+zip
  [switch]$SkipZip          # si solo quieres reportes
)

$ErrorActionPreference="Stop"

function _ts { (Get-Date).ToString("HH:mm:ss") }
function Ok([string]$m){ Write-Host ("[{0}]  OK   {1}" -f (_ts), $m) -ForegroundColor Green }
function Warn([string]$m){ Write-Host ("[{0}]  WARN {1}" -f (_ts), $m) -ForegroundColor Yellow }
function Info([string]$m){ Write-Host ("[{0}]       {1}" -f (_ts), $m) -ForegroundColor Gray }
function Die([string]$m){ Write-Host ("[{0}]  FAIL {1}" -f (_ts), $m) -ForegroundColor Red; exit 1 }

function Assert-RepoRoot {
  $need = @(
    ".\scripts\OMEGA_ship_batch.ps1",
    ".\scripts\patch_canonical_images_from_baseurl.py",
    ".\scripts\patch_shopify_images_from_canonical.py",
    ".\scripts\shopify_contract_gate.py"
  )
  foreach ($p in $need) { if (-not (Test-Path $p)) { Die "Falta en repo root: $p" } }
  Ok "repo root OK"
}

function Ensure-Tls12 {
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
}

function Clean-Url([string]$s){
  if (-not $s) { return $s }
  $reCf = [regex]'[\p{Cf}]'  # invisibles (ZWSP/LRM/etc)
  $t = $s
  try { $t = $t.Normalize([System.Text.NormalizationForm]::FormKC) } catch { }
  $t = $t -replace '[<>]',''
  $t = $reCf.Replace($t,'')
  $t = $t.Trim()
  return $t
}

function Get-HttpStatus([string]$url,[int]$timeoutMs){
  $u = Clean-Url $url
  if (-not $u) { return 0 }

  $sep = $(if ($u.Contains("?")) { "&" } else { "?" })
  $test = "$u${sep}cb=$(Get-Random)"

  try {
    $req = [System.Net.HttpWebRequest]::Create($test)
    $req.Method = "HEAD"
    $req.AllowAutoRedirect = $true
    $req.UserAgent = "Mozilla/5.0 (OMEGA-CONTROL)"
    $req.Timeout = $timeoutMs
    $req.ReadWriteTimeout = $timeoutMs

    $res = $req.GetResponse()
    $code = [int]$res.StatusCode
    $res.Close()
    return $code
  }
  catch [System.Net.WebException] {
    $we = $_.Exception
    if ($we.Response -ne $null) {
      try {
        $code = [int]$we.Response.StatusCode
        $we.Response.Close()
        return $code
      } catch { }
    }
    return 0
  }
  catch { return 0 }
}

function Run-ShipIfNeeded([string]$Batch,[string]$BaseMode,[switch]$Force){
  $finalCsv = "exports\releases\_batch\$Batch\shopify_import_all.FINAL.csv"
  $kitDir   = "exports\releases\_batch\$Batch\IMPORT_KIT"

  $needShip = $Force.IsPresent -or (-not (Test-Path $finalCsv)) -or (-not (Test-Path $kitDir))
  if (-not $needShip) {
    Ok "SHIP ya existe (FINAL + KIT). No corro ship."
    return
  }

  Info "Corriendo OMEGA_ship_batch.ps1 ..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\OMEGA_ship_batch.ps1 `
    -Batch $Batch `
    -BaseMode $BaseMode `
    -Repatch  # siempre repatch en control tower
  if ($LASTEXITCODE -ne 0) { Die "OMEGA_ship_batch falló." }

  Ok "SHIP OK"
}

function Csv-HasCol($rows, [string]$name){
  if (-not $rows -or $rows.Count -eq 0) { return $false }
  return $rows[0].PSObject.Properties.Name -contains $name
}

function Get-UniqueNonEmpty([string[]]$arr){
  if (-not $arr) { return @() }
  return ($arr | Where-Object { $_ -and $_.Trim().Length -gt 0 } | Select-Object -Unique)
}

function Lint-ShopifyCsv([string]$csvPath,[string]$outDir){
  if (-not (Test-Path $csvPath)) { Die "CSV no existe: $csvPath" }
  $rows = Import-Csv $csvPath
  if (-not $rows -or $rows.Count -eq 0) { Die "CSV vacío: $csvPath" }

  $issues = New-Object System.Collections.Generic.List[object]

  # ---- Handle checks ----
  if (Csv-HasCol $rows "Handle") {
    $handles = @($rows | ForEach-Object { $_.Handle })
    $handlesClean = @($handles | ForEach-Object { if ($_){ $_.ToString().Trim() } else { "" } })

    $emptyHandles = @($handlesClean | Where-Object { $_ -eq "" })
    if ($emptyHandles.Count -gt 0) {
      $issues.Add([pscustomobject]@{type="handle"; severity="error"; msg="Handles vacíos"; count=$emptyHandles.Count})
    }

    $dups = $handlesClean | Where-Object { $_ } | Group-Object | Where-Object { $_.Count -gt 1 }
    if ($dups.Count -gt 0) {
      $issues.Add([pscustomobject]@{type="handle"; severity="error"; msg="Handles duplicados"; count=$dups.Count})
      $dupPath = Join-Path $outDir "lint_handles_duplicados.txt"
      ($dups | ForEach-Object { "{0} x{1}" -f $_.Name, $_.Count }) | Set-Content -Encoding UTF8 $dupPath
    }

    # caracteres chistosos
    $weird = $handlesClean | Where-Object { $_ -match '[A-Z\s]' }
    if ($weird.Count -gt 0) {
      $issues.Add([pscustomobject]@{type="handle"; severity="warn"; msg="Handles con MAYUS o espacios (Shopify puede normalizar)"; count=$weird.Count})
      $p = Join-Path $outDir "lint_handles_weird_sample.txt"
      ($weird | Select-Object -First 50) | Set-Content -Encoding UTF8 $p
    }
  } else {
    $issues.Add([pscustomobject]@{type="schema"; severity="warn"; msg="No existe columna Handle"; count=1})
  }

  # ---- SKU uniqueness (si existe) ----
  if (Csv-HasCol $rows "Variant SKU") {
    $skus = @($rows | ForEach-Object { $_.'Variant SKU' })
    $skus = @($skus | ForEach-Object { if ($_){ $_.ToString().Trim() } else { "" } })
    $dupsSku = $skus | Where-Object { $_ } | Group-Object | Where-Object { $_.Count -gt 1 }
    if ($dupsSku.Count -gt 0) {
      $issues.Add([pscustomobject]@{type="sku"; severity="warn"; msg="SKUs duplicados (a veces OK, pero ojo)"; count=$dupsSku.Count})
      $p = Join-Path $outDir "lint_sku_duplicados.txt"
      ($dupsSku | ForEach-Object { "{0} x{1}" -f $_.Name, $_.Count }) | Set-Content -Encoding UTF8 $p
    }
  }

  # ---- Price numeric (si existe) ----
  if (Csv-HasCol $rows "Variant Price") {
    $badPrice = New-Object System.Collections.Generic.List[string]
    foreach ($r in $rows) {
      $v = $r.'Variant Price'
      if ($null -eq $v -or $v.ToString().Trim().Length -eq 0) { continue }
      $s = $v.ToString().Trim()
      [decimal]$d = 0
      $ok = [decimal]::TryParse($s, [ref]$d)
      if (-not $ok -or $d -lt 0) {
        $badPrice.Add("BAD_PRICE handle=$($r.Handle) price=[$s]")
      }
    }
    if ($badPrice.Count -gt 0) {
      $issues.Add([pscustomobject]@{type="price"; severity="error"; msg="Variant Price no numérico / negativo"; count=$badPrice.Count})
      $p = Join-Path $outDir "lint_price_bad.txt"
      $badPrice | Set-Content -Encoding UTF8 $p
    }
  }

  # ---- CSV injection (Excel/Sheets) ----
  $inj = New-Object System.Collections.Generic.List[string]
  foreach ($r in $rows) {
    foreach ($prop in $r.PSObject.Properties) {
      $val = $prop.Value
      if ($null -eq $val) { continue }
      $s = $val.ToString()
      if ($s.Length -gt 0 -and $s.Substring(0,1) -match '^[=\+\-@]$') {
        $inj.Add("INJECTION col=$($prop.Name) handle=$($r.Handle) value=$s")
      }
    }
  }
  if ($inj.Count -gt 0) {
    $issues.Add([pscustomobject]@{type="csv_injection"; severity="warn"; msg="Campos empiezan con = + - @ (riesgo Excel/Sheets)"; count=$inj.Count})
    $p = Join-Path $outDir "lint_csv_injection.txt"
    ($inj | Select-Object -First 500) | Set-Content -Encoding UTF8 $p
  }

  # ---- Output ----
  $lintPath = Join-Path $outDir "lint_summary.json"
  ($issues | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 $lintPath
  Ok "lint OK -> $lintPath"

  return @{
    rows = $rows.Count
    issues = $issues
    lint_path = $lintPath
  }
}

function UrlAudit-Parallel([string[]]$urls,[int]$timeoutMs,[int]$concurrency,[string]$outCsv,[string]$outBad){
  if (-not $urls -or $urls.Count -eq 0) { Die "No hay URLs para auditar." }

  Ensure-Tls12

  # runspace pool
  $min = 1
  $max = [Math]::Max(1, $concurrency)
  $pool = [RunspaceFactory]::CreateRunspacePool($min, $max)
  $pool.Open()

  $sb = {
    param($Url,$TimeoutMs)
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
    function Clean($s){
      if (-not $s) { return $s }
      $reCf = [regex]'[\p{Cf}]'
      $t=$s
      try { $t = $t.Normalize([System.Text.NormalizationForm]::FormKC) } catch { }
      $t = $t -replace '[<>]',''
      $t = $reCf.Replace($t,'')
      $t = $t.Trim()
      return $t
    }
    function Head($u,$ms){
      $u = Clean $u
      if (-not $u) { return 0 }
      $sep = $(if ($u.Contains("?")) { "&" } else { "?" })
      $test = "$u${sep}cb=$([int](Get-Random))"
      try {
        $req = [System.Net.HttpWebRequest]::Create($test)
        $req.Method="HEAD"
        $req.AllowAutoRedirect=$true
        $req.UserAgent="Mozilla/5.0 (OMEGA-AUDIT)"
        $req.Timeout=$ms
        $req.ReadWriteTimeout=$ms
        $res=$req.GetResponse()
        $code=[int]$res.StatusCode
        $res.Close()
        return $code
      } catch [System.Net.WebException] {
        $we=$_.Exception
        if ($we.Response -ne $null){
          try { $code=[int]$we.Response.StatusCode; $we.Response.Close(); return $code } catch { }
        }
        return 0
      } catch { return 0 }
    }

    $u = Clean $Url
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $code = Head $u $TimeoutMs
    $sw.Stop()

    [pscustomobject]@{
      url = $u
      http = $code
      ms = [int]$sw.ElapsedMilliseconds
    }
  }

  $jobs = New-Object System.Collections.Generic.List[object]
  foreach ($u in $urls) {
    $ps = [PowerShell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($sb).AddArgument($u).AddArgument($timeoutMs)
    $handle = $ps.BeginInvoke()
    $jobs.Add(@{ ps=$ps; handle=$handle })
  }

  $results = New-Object System.Collections.Generic.List[object]
  foreach ($j in $jobs) {
    $ps = $j.ps
    $h  = $j.handle
    try {
      $out = $ps.EndInvoke($h)
      foreach ($o in $out) { $results.Add($o) }
    } finally {
      $ps.Dispose()
    }
  }

  $pool.Close()
  $pool.Dispose()

  # write reports
  $results | Export-Csv -NoTypeInformation -Encoding UTF8 $outCsv

  $bad = $results | Where-Object { $_.http -ne 200 }
  if ($bad -and $bad.Count -gt 0) {
    ($bad | ForEach-Object { "{0} {1}" -f $_.http, $_.url }) | Set-Content -Encoding UTF8 $outBad
    Die "URL AUDIT FAIL: $($bad.Count) malas -> $outBad"
  }

  Ok "url audit OK -> $outCsv"
  return @{ total=$results.Count; ok=$results.Count; bad=0 }
}

function Make-Manifest([string]$batchDir,[string]$finalCsv,[string]$kitDir,[hashtable]$lint,[string]$urlAuditCsv){
  $hash = (Get-FileHash -Algorithm SHA256 $finalCsv).Hash
  $manifest = @{
    batch = (Split-Path $batchDir -Leaf)
    final_csv = $finalCsv
    final_csv_sha256 = $hash
    kit_dir = $kitDir
    rows = $lint.rows
    lint_summary = $lint.lint_path
    url_audit_csv = $urlAuditCsv
    generated_at = (Get-Date).ToString("s")
  } | ConvertTo-Json -Depth 8

  $p = Join-Path $batchDir "IMPORT_KIT\manifest.json"
  $manifest | Set-Content -Encoding UTF8 $p
  Ok "manifest OK -> $p"
  return $p
}

function Zip-Kit([string]$kitDir,[string]$outZip){
  if (-not (Test-Path $kitDir)) { Die "No existe kit: $kitDir" }
  if (Test-Path $outZip) { Remove-Item -Force $outZip }
  Compress-Archive -Path (Join-Path $kitDir "*") -DestinationPath $outZip -Force
  Ok "zip OK -> $outZip"
}

# ========================= RUN =========================
Assert-RepoRoot
Ensure-Tls12

$batchDir = "exports\releases\_batch\$Batch"
$finalCsv = Join-Path $batchDir "shopify_import_all.FINAL.csv"
$kitDir   = Join-Path $batchDir "IMPORT_KIT"

Run-ShipIfNeeded -Batch $Batch -BaseMode $BaseMode -Force:$Reship

if (-not (Test-Path $finalCsv)) { Die "No existe FINAL CSV: $finalCsv" }
if (-not (Test-Path $kitDir))   { Die "No existe IMPORT_KIT: $kitDir" }

# --- LINT ---
$lint = Lint-ShopifyCsv -csvPath $finalCsv -outDir $kitDir

# --- URL AUDIT ---
$urlAuditCsv = Join-Path $kitDir "url_audit.csv"
$urlBadTxt   = Join-Path $kitDir "url_audit.bad.txt"

if (-not $SkipUrlAudit) {
  $rows = Import-Csv $finalCsv
  if (Csv-HasCol $rows "Image Src") {
    $urls = @(
      $rows |
      Where-Object { $_.'Image Src' } |
      Select-Object -ExpandProperty 'Image Src' -Unique |
      ForEach-Object { Clean-Url $_ }
    )
    $urls = Get-UniqueNonEmpty $urls

    if (-not $urls -or $urls.Count -eq 0) { Die "No hay Image Src para auditar." }

    Info ("url audit unique=" + $urls.Count + " concurrency=" + $Concurrency)
    UrlAudit-Parallel -urls $urls -timeoutMs $TimeoutMs -concurrency $Concurrency -outCsv $urlAuditCsv -outBad $urlBadTxt | Out-Null
  } else {
    Warn "No existe columna 'Image Src' -> me salto url audit"
  }
} else {
  Warn "SkipUrlAudit activado"
}

# --- MANIFEST ---
$manifestPath = Make-Manifest -batchDir $batchDir -finalCsv $finalCsv -kitDir $kitDir -lint $lint -urlAuditCsv $urlAuditCsv

# --- ZIP ---
if (-not $SkipZip) {
  $stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
  $zip = Join-Path $batchDir ("IMPORT_KIT_{0}_{1}.zip" -f $Batch, $stamp)
  Zip-Kit -kitDir $kitDir -outZip $zip
} else {
  Warn "SkipZip activado"
}

Ok "DONE"
Ok "FINAL CSV: $finalCsv"
Ok "KIT DIR:   $kitDir"
Ok "MANIFEST:  $manifestPath"
