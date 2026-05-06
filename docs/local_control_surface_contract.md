# Local Control Surface Contract

Status: local-only pre-web surface
Scope: SYNAPSE / Trendify Fase 1
Owner: human operator + repository guardrails

## Purpose

The local control surface is the bridge between a terminal-only system and a future web or dashboard interface.

It exists to make SYNAPSE usable from a controlled local launcher before Shopify, Meta, real spend, public web, or secrets are introduced.

## Non-negotiable boundaries

- LIVE=0
- SPEND=0
- SECRETS=0
- SHOPIFY=PAUSED
- PUBLIC_WEB=0
- REAL_CUSTOMER_TRAFFIC=0
- ARBITRARY_SHELL=0
- TOKEN_INPUT=0
- API_WRITE_ACTIONS=0

## Canonical launcher

scripts/synapse_control_surface.py

## Required modes

- --check
- --list
- --json
- --run <whitelisted_command_id>

## Current command catalog

The catalog is intentionally read-only and help-oriented.

Required command ids:

- phase1_ready_help
- ops_summary_help
- meta_autopilot_help
- post_learning_help
- creative_queue_help
- creative_briefs_help
- run_candidates_demo_help

## Security contract

The control surface must:

- use only a hardcoded whitelist
- reject unknown command ids
- avoid arbitrary shell execution
- force dry-run and no-live environment variables
- not require tokens
- not require Shopify setup
- not require Meta setup
- not spend money
- not write secrets
- not publish or launch anything
- not connect to live customer traffic

## Acceptance criteria

A valid local control surface must satisfy:

- whitelisted commands >= 6
- unknown command execution blocked
- --check exits 0
- --list exits 0
- --json exits 0 and parses as JSON
- LOCAL_CONTROL_SURFACE_OK=1
- LIVE=0
- SPEND=0
- SECRETS=0
- SHOPIFY=PAUSED
- ARBITRARY_SHELL=0 documented
- scripts/synapse_control_surface.py documented

## Deferred

This is not the final web UI. It is a safe local operator surface.

Deferred until later gates:

- public web app
- Shopify Admin API integration
- Meta API live execution
- paid traffic
- real customer traffic
- API tokens
- webhook creation
- domain purchase
