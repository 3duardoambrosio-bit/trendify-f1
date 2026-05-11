# A8-R42O — Real Asset Capture Placement Gate

## Purpose

A8-R42O creates the local placement gate for the three real video exports required before the first manual zero-spend publish.

## Current expected state

- READY_FOR_ASSET_CAPTURE_EXECUTION=1
- READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH=0
- MISSING_REAL_ASSET_COUNT=3
- REAL_ASSET_EXPORT_COUNT=0

## What this front produces

- real asset capture placement JSON;
- real asset capture placement Markdown;
- capture slot CSV;
- source dropzone folders;
- copy plan PowerShell script.

## Rule

The system must not unlock first publish until the three real video exports exist and are copied into the expected handoff export slots.

## Next front

A8-R42P: place real exported assets into handoff slots and re-run first publish validation.
