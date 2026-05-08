# A8-R30 — Claude Reentry Protocol

## Purpose

Claude is not a blocking dependency. During Claude downtime, SYNAPSE advances through local high-integrity controls:

- local gates
- executable contracts
- PowerShell/.NET strict scans
- post-commit ZIP evidence
- SHA256 checkpoints
- normal commits with real hooks

## Reentry Rule

When Claude is available again, Claude must audit the full delta produced during downtime, not only the latest file.

## Required Inputs For Claude

Provide:

1. Latest validated ZIP before Claude downtime.
2. Latest validated ZIP after local-only work.
3. Commit range from last externally audited checkpoint to current HEAD.
4. This reentry protocol.
5. List of new contracts added during downtime.
6. Latest gate logs and SHA256 values.

## Claude Audit Questions

Ask Claude to evaluate:

1. Did any local-only island create a false green risk?
2. Did any evidence contract become too static, brittle, or incomplete?
3. Does the bundle evidence remain enough for independent review?
4. What is the highest-ROI next island after reviewing the full delta?
5. Is there any blocker before returning to product-facing control surface work?

## Current Local-Only Direction

A8-R30 seals A8-R29 by adding an executable bundle self-test contract.

A8-R29 result became clean once.
A8-R30 makes that cleanliness enforceable.
