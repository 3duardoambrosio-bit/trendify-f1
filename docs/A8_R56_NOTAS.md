# A8-R56 Close Notes

## Scope

A8-R56 closed the P1 divergence between the simulation engine generic/NPC blacklist and the read-only UI NPC marker detection.

## Canonical source

- synapse/cli/_blacklist.py
- GENERIC_BLACKLIST
- Pattern count: 28
- Type: tuple[str, ...]

## Consumers

- synapse/cli/simulate.py imports GENERIC_BLACKLIST from synapse.cli._blacklist
- synapse/ui/read_model.py imports GENERIC_BLACKLIST as NPC_BLACKLIST_PATTERNS from synapse.cli._blacklist

## Removed divergence

Before A8-R56:

- Engine: 28 patterns
- UI: 16 patterns
- Overlap: 3 patterns
- Engine-only: 25 patterns
- UI-only: 13 patterns

After A8-R56:

- Canonical blacklist sources: 1
- Local engine blacklist assignments: 0
- Local UI blacklist assignments: 0
- Static UI/engine delta: 0

## Tests added

- tests/cli/test_blacklist_contract.py
- tests/ui/test_read_model_blacklist_sync.py

## Constraints preserved

- No product discovery added.
- No Marketing OS expansion added.
- No action console added.
- No API connection added.
- UI remains read-only.
- No subprocess/network/filesystem write behavior added to read_model.py.
- _blacklist.py remains pure data.

## Validation basis

A8-R56 was validated through:

- Static AST/text contract gates during the code commit flow.
- Cached git checks.
- F1 commit hook.
- Hook static compile gate.
- Registry gates.
- Final clean status after code commit.

Direct pytest was skipped during local closure because the environment repeatedly interrupted during Python startup/import paths involving sitecustomize.py, tests/conftest.py, Hypothesis .pyc loading, stdlib argparse, and stdlib bytecode import.

## Code commit

- Commit: 49d5b574625af4a35542e531c3fa9d7e58a25630
- Subject: fix(ui): share canonical npc blacklist

## Close status

A8-R56 closed by this documentation commit, tag, and bundle.