# A8-R42B — Product Decision Packet Local

## Purpose

This module converts product candidates into a local decision packet.

It does not require full automation. It supports assisted selling.

## Input

JSON list of product candidates with:

- name
- target_buyer
- pain_or_desire
- estimated_margin_pct
- wow_factor
- problem_intensity
- content_potential
- supplier_risk
- competition_risk
- complexity_risk

## Output

- all product decision packets
- best product packet JSON
- best product packet Markdown
- decision: ADVANCE / WATCHLIST / REJECT
- first test checklist

## Next operational use

Feed real product candidates into this tool.

Then use the best packet to build:

1. offer;
2. listing;
3. content hooks;
4. first manual test.
