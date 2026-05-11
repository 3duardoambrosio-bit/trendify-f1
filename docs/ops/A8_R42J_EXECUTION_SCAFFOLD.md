# A8-R42J — Execution Folder Scaffold

## Purpose

A8-R42J creates a local execution folder scaffold for the first publish assets.

## Product

Rechargeable Electric Lint Remover.

## Output

The tool generates:

- execution scaffold JSON;
- execution scaffold Markdown;
- asset manifest JSON;
- asset manifest CSV;
- raw video folders;
- export folders;
- caption files;
- publish record templates;
- per-asset publish record placeholders;
- metric record templates;
- per-asset metric record placeholders;
- supplier evidence folder;
- decision log.

## Operating rule

This remains local-only.

- cloud_used: 0
- web_used: 0
- source_mode: LOCAL_CURATED_INPUT

## Execution rule

No ads, no inventory, no supplier commitment before manual signal and supplier evidence.

## Fix note

A8-R42J-B anchors generated per-asset files under `out_dir` so the execution scaffold is self-contained and does not write accidental relative folders into the repo root.

## Next front

A8-R42K: first publish operator checklist and offline execution packet.
