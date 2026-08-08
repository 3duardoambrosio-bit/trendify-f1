[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Csv = '',

    [string]$Workspace = '.\artifacts\operator_workspace',

    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$SafetyEnvironmentNames = @(
    'PYTEST_DISABLE_PLUGIN_AUTOLOAD',
    'SYNAPSE_SHOPIFY_ENABLED',
    'SYNAPSE_SHOPIFY_LIVE',
    'SYNAPSE_DROPI_LIVE',
    'SYNAPSE_META_LIVE',
    'SYNAPSE_LIVE_WRITE',
    'SYNAPSE_DRY_RUN'
)
$PreviousEnvironment = @{}

function Resolve-SynapsePython {
    param([string]$Root)

    $Candidates = @()

    if (-not [string]::IsNullOrWhiteSpace($env:VIRTUAL_ENV)) {
        $Candidates += Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
    }

    $Candidates += Join-Path $Root 'venv\Scripts\python.exe'

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    }

    $Command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        $Command = Get-Command python -ErrorAction SilentlyContinue
    }

    if ($null -ne $Command) {
        return $Command.Source
    }

    throw 'OPERATOR_LAUNCHER_ERROR=PYTHON_NOT_FOUND'
}

function Save-SafetyEnvironment {
    foreach ($Name in $SafetyEnvironmentNames) {
        $PreviousEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
}

function Set-FailClosedEnvironment {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    $env:SYNAPSE_SHOPIFY_ENABLED = '0'
    $env:SYNAPSE_SHOPIFY_LIVE = '0'
    $env:SYNAPSE_DROPI_LIVE = '0'
    $env:SYNAPSE_META_LIVE = '0'
    $env:SYNAPSE_LIVE_WRITE = '0'
    $env:SYNAPSE_DRY_RUN = '1'
}

function Restore-SafetyEnvironment {
    foreach ($Name in $SafetyEnvironmentNames) {
        $Value = $PreviousEnvironment[$Name]
        if ($null -eq $Value) {
            Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($Name, [string]$Value, 'Process')
        }
    }
}

Push-Location $RepoRoot
Save-SafetyEnvironment

try {
    Write-Host '=== SYNAPSE PHASE 1 - OPERATOR LAUNCHER ==='
    Write-Host 'MODE=LOCAL_ONLY'
    Write-Host 'NETWORK_AUTHORIZED=false'
    Write-Host 'LIVE_WRITES_AUTHORIZED=false'
    Write-Host 'REAL_SPEND_AUTHORIZED=false'
    Write-Host 'OPERATOR_IN_CONTROL=true'

    if ([string]::IsNullOrWhiteSpace($Csv)) {
        $Csv = Read-Host 'Ruta del CSV de productos'
    }

    if ([string]::IsNullOrWhiteSpace($Csv)) {
        throw 'OPERATOR_LAUNCHER_ERROR=CSV_REQUIRED'
    }

    if ($Csv -match '^https?://') {
        throw 'OPERATOR_LAUNCHER_ERROR=REMOTE_CSV_FORBIDDEN'
    }

    try {
        $CsvPath = (Resolve-Path -LiteralPath $Csv -ErrorAction Stop).Path
    }
    catch {
        throw "OPERATOR_LAUNCHER_ERROR=CSV_NOT_FOUND path=$Csv"
    }

    if (-not (Test-Path -LiteralPath $CsvPath -PathType Leaf)) {
        throw "OPERATOR_LAUNCHER_ERROR=CSV_NOT_FILE path=$CsvPath"
    }

    if ([System.IO.Path]::GetExtension($CsvPath) -ine '.csv') {
        throw 'OPERATOR_LAUNCHER_ERROR=CSV_EXTENSION_REQUIRED'
    }

    if ([System.IO.Path]::IsPathRooted($Workspace)) {
        $WorkspacePath = [System.IO.Path]::GetFullPath($Workspace)
    }
    else {
        $WorkspacePath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Workspace))
    }

    $Python = Resolve-SynapsePython -Root $RepoRoot

    & $Python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)'
    if ($LASTEXITCODE -ne 0) {
        throw 'OPERATOR_LAUNCHER_ERROR=PYTHON_3_10_REQUIRED'
    }

    $PythonVersion = (& $Python --version 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw 'OPERATOR_LAUNCHER_ERROR=PYTHON_VERSION_CHECK_FAILED'
    }

    Set-FailClosedEnvironment

    Write-Host "PYTHON=$Python"
    Write-Host "PYTHON_VERSION=$PythonVersion"
    Write-Host "CSV=$CsvPath"
    Write-Host "WORKSPACE_DIR=$WorkspacePath"

    Write-Host ''
    Write-Host '=== BUILD OPERATOR WORKSPACE ==='

    & $Python -m synapse.ui.operator_enrichment_cli rebuild `
        --csv $CsvPath `
        --workspace $WorkspacePath

    $RebuildExit = $LASTEXITCODE
    if ($RebuildExit -ne 0) {
        throw "OPERATOR_LAUNCHER_ERROR=REBUILD_FAILED exit=$RebuildExit"
    }

    $WorkspaceHtml = Join-Path $WorkspacePath 'workspace.html'
    $ReportJson = Join-Path $WorkspacePath 'intake_report.json'

    if (-not (Test-Path -LiteralPath $WorkspaceHtml -PathType Leaf)) {
        throw 'OPERATOR_LAUNCHER_ERROR=WORKSPACE_HTML_MISSING'
    }

    if (-not (Test-Path -LiteralPath $ReportJson -PathType Leaf)) {
        throw 'OPERATOR_LAUNCHER_ERROR=INTAKE_REPORT_MISSING'
    }

    Write-Host ''
    Write-Host '=== READY ==='
    Write-Host "WORKSPACE_HTML=$WorkspaceHtml"
    Write-Host "INTAKE_REPORT=$ReportJson"

    if ($NoOpen) {
        Write-Host 'WORKSPACE_OPENED=false'
    }
    else {
        Start-Process $WorkspaceHtml
        Write-Host 'WORKSPACE_OPENED=true'
    }

    Write-Host 'NETWORK=false'
    Write-Host 'LIVE_WRITE=false'
    Write-Host 'REAL_SPEND=false'
    Write-Host 'OPERATOR_LAUNCHER=PASS'
}
finally {
    Restore-SafetyEnvironment
    Pop-Location
}
