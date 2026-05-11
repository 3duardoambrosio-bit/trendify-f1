# A8-R42N — First-Publish Operator Validation

## Purpose

A8-R42N validates the A8-R42M operator handoff before the first manual zero-spend publish.

## Rule

The system must not claim first-publish readiness until real export videos exist.

## Expected current state

The current handoff is structurally ready, but real video exports are not expected yet.

Expected validation result:

- READY_FOR_REAL_ASSET_SLOT_PREPARATION=1
- READY_FOR_FIRST_MANUAL_ZERO_SPEND_PUBLISH=0

## Why

Publishing requires three real exported videos. The handoff contains the execution structure, packets, captions, publish records, metric records and decision rules. It does not automatically create real video assets.

## Next front

A8-R42O: real asset capture placement / first manual zero-spend publish gate.
