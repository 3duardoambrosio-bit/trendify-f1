# ============================================================
# SYNAPSE FIXPACK (SAFE RUNNER)
# Repo: C:\Users\edu_a\OneDrive\Documentos\trendify-fase1
# Objetivo: Doctor GREEN (rápido) + output claro
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "=== FIXPACK START ==="
Write-Host "PWD: $PWD"

$py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
Write-Host "Python: $py"

python --version
python -m synapse.infra.doctor

Write-Host "=== FIXPACK END ==="
