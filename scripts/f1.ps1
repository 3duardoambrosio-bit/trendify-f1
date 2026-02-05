param(
  [ValidateSet("dev","ops","release","status","rollback")] [string]$Cmd = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Die([string]$m){ Write-Host $m; exit 1 }
function Status-Lines { return (git status --porcelain | Measure-Object).Count }

if (-not (Test-Path ".git")) { Die "NO .git (root incorrecto)" }
if (-not (Test-Path "pyproject.toml")) { Die "NO pyproject.toml (root incorrecto)" }

if ($Cmd -eq "status") {
  "ROOT={0}" -f (Get-Location).Path
  "BRANCH={0}" -f (git rev-parse --abbrev-ref HEAD)
  "STATUS_LINES={0}" -f (Status-Lines)
  "HOOKS_PATH={0}" -f (git config core.hooksPath)
  "FILES_GATE={0}" -f (Test-Path scripts\gate_f1.ps1)
  "FILES_INSTALL_HOOKS={0}" -f (Test-Path scripts\install_hooks.ps1)
  exit 0
}

if ($Cmd -eq "rollback") {
  git restore --source=HEAD --staged --worktree -- . | Out-Null
  git clean -fd | Out-Null
  "STATUS_LINES={0}" -f (Status-Lines)
  exit 0
}

if (-not (Test-Path "scripts\gate_f1.ps1")) { Die "NO scripts\gate_f1.ps1" }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate_f1.ps1 -Mode $Cmd
$ec = $LASTEXITCODE
"GATE_EXITCODE={0}" -f $ec
exit $ec
