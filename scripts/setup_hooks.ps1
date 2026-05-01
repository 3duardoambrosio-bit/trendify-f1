$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel).Trim()
Set-Location -LiteralPath $root

git config core.hooksPath .githooks
$value = (git config --get core.hooksPath).Trim()

Write-Host "CORE_HOOKS_PATH=$value"

if ($value -ne ".githooks") {
  throw "CORE_HOOKS_PATH_NOT_SET=$value"
}

if (-not (Test-Path -LiteralPath ".githooks\pre-commit")) {
  throw "PRE_COMMIT_HOOK_MISSING"
}

Write-Host "SETUP_HOOKS_OK=1"
