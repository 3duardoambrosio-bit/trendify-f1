# A8-R105 — Independent Marketing Expert Audit Protocol

## Purpose

A8-R105 is not another engine implementation island.

It creates a blind expert-audit pack for the R104 marketing decision engine.

The goal is to evaluate whether the engine's outputs are marketing-expert-correct, not merely structurally valid.

## Closed chain under audit

- R101: methodology depth spec.
- R102: executable rule contract.
- R103: loader + adversarial fixtures.
- R104: local decision engine replacing `_category_angle`.

## Independence rule

The R105 blind cases do not include:

- target rule id
- expected engine status
- expected trigger
- expected rule id
- expected pass/fail label for the engine

The expert auditor must score the engine outputs against the rubric.

## Non-goals

- No engine code changes.
- No rule tuning.
- No live Meta.
- No spend.
- No external writes.
- No order creation.
- No commerce-side action.
- No market validation claim.

## Close rule

R105 closes only if an external expert audit confirms that the engine outputs are strong enough as marketing decisions, not merely executable outputs.

R105 does not certify sales performance. Sales validation remains future work.