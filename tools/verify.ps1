$ErrorActionPreference = "Stop"

Write-Host "== SYNAPSE VERIFY =="

Write-Host "`n[1/3] Doctor"
python -m synapse.infra.doctor

Write-Host "`n[2/3] Pytest"
pytest -q

Write-Host "`n[3/3] Git status"
git status

Write-Host "`nOK: verify completo"
