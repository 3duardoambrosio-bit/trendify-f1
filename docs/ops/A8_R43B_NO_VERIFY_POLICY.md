# A8-R43B — Commit Hook Bypass Policy

## Purpose

Prevent the repository from normalizing commit hook bypass behavior.

## Rule

Normal commits must go through configured hooks.

## Forbidden behavior

- Do not document bypass commands as an accepted workflow.
- Do not add shell snippets that skip hooks.
- Do not add scripts that teach operators to bypass the F1 gate.
- Do not preserve the exact bypass flag literal in tracked text.

## Accepted language

The repository may discuss bypass behavior as policy language, but the exact bypass flag literal must not appear in tracked text.

## Validation

`tools/a8_no_verify_policy_check.py` performs the direct repository text check.
`tests/meta/test_no_verify_policy.py` validates the policy surface and checker presence.
