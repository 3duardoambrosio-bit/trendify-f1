# CODEX.md  Onboarding rápido para agentes (Codex / ChatGPT / Claude)

## Objetivo
Operar en SYNAPSE/Trendify F1 con cambios pequeños, verificables, y reproducibles.
Regla: ACERO, NO HUMO.

## Comandos sagrados (siempre)
- python -m synapse.infra.doctor
- pytest -q
- git status

## Qué NO tocar / NO versionar
- outputs generados en exports/** (incluye releases y sha256)
- secretos: .env, llaves, credenciales

## Zonas de trabajo
- Código: synapse/**
- Tests: tests/**
- Config/data determinística: data/**

## Estilo de cambios
- Un PR/commit = una intención.
- Si falla algo, arreglar antes de avanzar.
- No meter artefactos generados al repo.

## Checklist antes de push
1) python -m synapse.infra.doctor
2) pytest -q
3) git status (clean)
