# AGENTS.md  Trendify F1 / SYNAPSE
Regla: ACERO, NO HUMO. Cambios pequeños, verificables, y con comandos reproducibles.

## Objetivo
Este repo es un sistema operativo para e-commerce (SYNAPSE/Trendify F1).
Los artefactos generados NO se versionan (exports/releases, sha256, etc).

## Comandos de verificación (los 3 sagrados)
- python -m synapse.infra.doctor
- pytest -q
- git status

## Políticas de repo
- No versionar outputs generados:
  - exports/releases/**
  - exports/**/*.sha256
  - exports/** (salvo templates explícitos)
- No tocar secretos:
  - Nunca commitear .env, llaves, credenciales.
  - Usar exports/secrets_template.env como plantilla.

## Qué sí es source of truth
- Código: synapse/**
- Config / data determinística: data/**
- Tests: tests/**

## Qué es output
- exports/** (artefactos generados)
- data/run, data/ledger, evidence, backups, etc (según .gitignore)

## Estándar de cambios
- Cada cambio debe dejar el repo pasando doctor + pytest.
- Si se mueven rutas, actualizar docs y scripts asociados.
