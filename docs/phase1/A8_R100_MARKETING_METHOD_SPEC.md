# A8-R100 — Marketing Methodology Spec / Expert Playbook V1

RESULT=DRAFT_A8_R100I1_MARKETING_METHOD_SPEC_READY_FOR_AUDIT

## Scope

- This is a methodology spec.
- It is not a loader.
- It is not a decision engine.
- It does not certify market performance.
- It does not allow live Meta, Shopify, Dropi, spend, orders, or fulfillment.

## Audit gates
- required_framework_count: 15
- required_fields: ['name', 'purpose', 'accepted_inputs', 'required_outputs', 'preconditions', 'decision_rules', 'rejection_rules', 'trace_fields', 'source_anchors', 'conversion_target', 'anti_generic_rules', 'determinism', 'worked_example']
- zero_missing_required_fields: True
- min_source_anchors_per_framework: 1
- min_anti_generic_rules_per_framework: 1
- worked_example_required_per_framework: True
- deterministic_rules_required: True
- tie_break_and_fallback_required: True

## Source anchor families
- stp: HBS/STP family: segmentation, target selection, positioning.
- jtbd: HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- awareness: Buyer-state/direct-response awareness logic.
- persuasion: Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- claims: Claim substantiation and risk-control logic.
- synapse: SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.
- channel: Channel-specific creative constraint logic.

## Frameworks

### AudiencePersona

Purpose: Choose a specific buyer segment/persona from product facts, JTBD, and commercial constraints.

Accepted inputs:
- product_category
- product_facts
- price_band
- margin_profile
- known_use_cases
- channel

Required outputs:
- audience_segment
- persona_hypothesis
- buyer_job
- specificity_score

Decision rules:
- AUD-001: WHEN product facts imply a concrete use situation THEN select persona tied to that situation, not a demographic stereotype PRIORITY=80
- AUD-002: WHEN margin or CAC constraints are tight THEN prefer audience with higher purchase intent and lower education burden PRIORITY=70

Rejection rules:
- Reject audience if it could apply to every product in the category.
- Reject pure demographic persona without job/use-case evidence.

Anti-generic rules:
- Generic if persona lacks product fact, job, or buying situation.
- Generic if persona is only age/gender/income without purchase context.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- HBS/STP family: segmentation, target selection, positioning.
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `AudienceRule`

Worked example:
```json
{
  "input": {
    "channel": "Meta",
    "price_band": "low-mid",
    "product_category": "pet",
    "product_facts": [
      "portable water bowl",
      "leak resistant"
    ]
  },
  "output": {
    "audience_segment": "dog owners who walk/travel with pets",
    "buyer_job": "keep dog hydrated outside home without mess",
    "specificity_score": 0.82
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "AudiencePersona",
    "operator_review_required": false,
    "rule_ids_applied": [
      "AUD-001"
    ],
    "source_anchors_used": [
      "HBS/STP family: segmentation, target selection, positioning."
    ]
  }
}
```

### BuyerStateAwareness

Purpose: Classify buyer awareness/friction state so messaging matches how much education and proof is needed.

Accepted inputs:
- audience_segment
- product_category
- problem_visibility
- market_familiarity
- proof_available

Required outputs:
- buyer_state
- education_depth
- proof_depth
- message_directness

Decision rules:
- BSA-001: WHEN buyer knows the problem and product type THEN use direct problem-solution framing PRIORITY=70
- BSA-002: WHEN problem is latent or shame/friction sensitive THEN use situation-first framing and softer CTA PRIORITY=65

Rejection rules:
- Reject buyer state if no evidence supports awareness level.
- Reject high-directness CTA when proof is weak and buyer state is cold.

Anti-generic rules:
- Generic if awareness state does not change hook, proof, CTA, or offer.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Buyer-state/direct-response awareness logic.
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `BuyerStateRule`

Worked example:
```json
{
  "input": {
    "market_familiarity": "medium",
    "problem_visibility": "high",
    "proof_available": [
      "demo photo"
    ]
  },
  "output": {
    "buyer_state": "problem-aware",
    "education_depth": "medium",
    "message_directness": "direct",
    "proof_depth": "demo-required"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "BuyerStateAwareness",
    "operator_review_required": false,
    "rule_ids_applied": [
      "BSA-001"
    ],
    "source_anchors_used": [
      "Buyer-state/direct-response awareness logic."
    ]
  }
}
```

### ProductFactExtraction

Purpose: Extract marketing-usable facts from product/evaluation data without inventing claims.

Accepted inputs:
- title
- description
- category
- supplier_cost
- landed_cost
- sale_price
- attributes
- available_media

Required outputs:
- facts_allowed
- facts_missing
- claim_limits
- proof_gaps

Decision rules:
- PFX-001: WHEN fact exists in source data THEN allow it as product_facts_used PRIORITY=90
- PFX-002: WHEN benefit is inferred but not proven THEN mark as hypothesis and require proof PRIORITY=80

Rejection rules:
- Reject unsupported medical, guaranteed, absolute, or performance claims.
- Reject benefit if it is not traceable to source data or proof.

Anti-generic rules:
- Generic if output uses category clichés instead of extracted product facts.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Claim substantiation and risk-control logic.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `ProductFactRule`

Worked example:
```json
{
  "input": {
    "attributes": [
      "foldable",
      "leak resistant"
    ],
    "available_media": [
      "photo"
    ],
    "title": "Portable Leak Resistant Pet Bowl"
  },
  "output": {
    "claim_limits": [
      "do not claim vet-approved"
    ],
    "facts_allowed": [
      "foldable",
      "leak resistant"
    ],
    "proof_gaps": [
      "needs real use demo"
    ]
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ProductFactExtraction",
    "operator_review_required": false,
    "rule_ids_applied": [
      "PFX-001"
    ],
    "source_anchors_used": [
      "Claim substantiation and risk-control logic."
    ]
  }
}
```

### ValuePropositionPositioning

Purpose: Define why this product should be chosen by the selected segment versus alternatives.

Accepted inputs:
- audience_segment
- buyer_job
- product_facts
- price_band
- competitive_alternatives

Required outputs:
- positioning_statement
- primary_value
- tradeoff
- reason_to_choose

Decision rules:
- POS-001: WHEN product solves a specific job with concrete facts THEN position around job completion not category label PRIORITY=80
- POS-002: WHEN price is not lowest THEN position around convenience/proof/value, not cheapness PRIORITY=70

Rejection rules:
- Reject positioning if it says only best/high-quality/amazing without concrete tradeoff.

Anti-generic rules:
- Generic if positioning could be pasted onto any similar SKU.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- HBS/STP family: segmentation, target selection, positioning.
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `PositioningRule`

Worked example:
```json
{
  "input": {
    "buyer_job": "hydrate dog during walks",
    "competitive_alternatives": [
      "regular bottle",
      "bulky bowl"
    ],
    "product_facts": [
      "foldable",
      "leak resistant"
    ]
  },
  "output": {
    "positioning_statement": "A compact walk/travel hydration helper for dog owners who want less mess outside home.",
    "primary_value": "portable mess reduction"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ValuePropositionPositioning",
    "operator_review_required": false,
    "rule_ids_applied": [
      "POS-001"
    ],
    "source_anchors_used": [
      "HBS/STP family: segmentation, target selection, positioning."
    ]
  }
}
```

### AngleSelection

Purpose: Select the advertising angle from product facts, buyer state, proof, claim risk, channel, and economics.

Accepted inputs:
- audience_segment
- buyer_state
- product_facts
- proof_available
- claim_risk
- channel
- margin_profile

Required outputs:
- angle_type
- mechanism
- proof_required
- angle_trace

Decision rules:
- ANG-001: WHEN specific use-case fact and demo proof exist THEN use demonstration/use-case angle PRIORITY=90
- ANG-002: WHEN proof is weak or claim risk high THEN use low-claim situational angle PRIORITY=85

Rejection rules:
- Reject angle if it relies on unsupported transformation or guaranteed result.
- Reject category-only angle if a product-specific fact is available.

Anti-generic rules:
- Generic if angle can apply to all products in category without changing.
- Generic if angle ignores buyer state, proof, or channel.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- HBS/STP family: segmentation, target selection, positioning.
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- Claim substantiation and risk-control logic.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `AngleRule`

Worked example:
```json
{
  "input": {
    "buyer_state": "problem-aware",
    "claim_risk": "low",
    "product_facts": [
      "foldable",
      "leak resistant"
    ],
    "proof_available": [
      "demo photo"
    ]
  },
  "output": {
    "angle_type": "situational demonstration",
    "mechanism": "show less-mess hydration during walks",
    "proof_required": [
      "short demo"
    ]
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "AngleSelection",
    "operator_review_required": false,
    "rule_ids_applied": [
      "ANG-001"
    ],
    "source_anchors_used": [
      "HBS/STP family: segmentation, target selection, positioning."
    ]
  }
}
```

### OfferConstruction

Purpose: Construct a safe offer promise matched to segment objection, economics, proof, and operator constraints.

Accepted inputs:
- audience_segment
- objections
- sale_price
- margin_profile
- proof_available
- fulfillment_constraints

Required outputs:
- offer_promise
- offer_mechanism
- risk_reversal
- offer_limits

Decision rules:
- OFF-001: WHEN buyer objection is convenience/friction THEN offer promise must reduce that friction with a product fact PRIORITY=80
- OFF-002: WHEN margin is tight THEN avoid discount-dependent offer unless explicitly allowed PRIORITY=75

Rejection rules:
- Reject offer if it promises unsupported outcomes.
- Reject discount offer if margin guard would fail.

Anti-generic rules:
- Generic if offer is just buy now / limited time without product-specific value.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `OfferRule`

Worked example:
```json
{
  "input": {
    "margin_profile": "acceptable",
    "objections": [
      "will it leak?",
      "is it bulky?"
    ],
    "proof_available": [
      "demo photo"
    ]
  },
  "output": {
    "offer_mechanism": "foldable leak-resistant design",
    "offer_promise": "portable hydration without carrying a bulky bowl",
    "risk_reversal": "operator review required for guarantee wording"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "OfferConstruction",
    "operator_review_required": false,
    "rule_ids_applied": [
      "OFF-001"
    ],
    "source_anchors_used": [
      "HBR/JTBD family: customer job, context, functional/social/emotional motivation."
    ]
  }
}
```

### HookConstruction

Purpose: Create hooks tied to a product fact, buyer state, objection, proof need, and channel constraint.

Accepted inputs:
- angle_type
- product_facts
- buyer_state
- objection
- proof_required
- channel

Required outputs:
- hook_text
- hook_type
- visual_prompt
- required_proof

Decision rules:
- HOK-001: WHEN demo proof exists THEN hook should make the proof visible in first frame/line PRIORITY=90
- HOK-002: WHEN objection is concrete THEN hook should answer that objection without overclaiming PRIORITY=80

Rejection rules:
- Reject hook if it lacks product fact or buyer situation.
- Reject hook if it requires proof not available.

Anti-generic rules:
- Generic if hook could run for any product after replacing the noun.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- Buyer-state/direct-response awareness logic.
- Channel-specific creative constraint logic.
- Claim substantiation and risk-control logic.

Conversion target: `HookRule`

Worked example:
```json
{
  "input": {
    "angle_type": "situational demonstration",
    "channel": "Meta",
    "objection": "bulky",
    "product_facts": [
      "foldable"
    ]
  },
  "output": {
    "hook_text": "No cargues un bowl gigante para una caminata corta.",
    "hook_type": "objection-led",
    "visual_prompt": "show bulky alternative vs foldable bowl"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "HookConstruction",
    "operator_review_required": false,
    "rule_ids_applied": [
      "HOK-001"
    ],
    "source_anchors_used": [
      "Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity."
    ]
  }
}
```

### ObjectionHandling

Purpose: Map buyer objections to proof, copy angle, and operator review requirements.

Accepted inputs:
- audience_segment
- buyer_state
- price_band
- product_facts
- common_objections
- proof_available

Required outputs:
- objection_map
- response_strategy
- proof_needed
- operator_review_flags

Decision rules:
- OBJ-001: WHEN objection is product quality THEN require demo/detail proof before claim PRIORITY=85
- OBJ-002: WHEN objection is price THEN answer with job/value tradeoff, not unsupported superiority PRIORITY=70

Rejection rules:
- Reject objection response that creates an unsupported claim.

Anti-generic rules:
- Generic if objections are generic trust/price only without segment/product specificity.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- HBR/JTBD family: customer job, context, functional/social/emotional motivation.
- Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- Claim substantiation and risk-control logic.

Conversion target: `ObjectionRule`

Worked example:
```json
{
  "input": {
    "common_objections": [
      "will it leak?",
      "will my dog use it?"
    ],
    "proof_available": [
      "photo"
    ]
  },
  "output": {
    "objection_map": [
      {
        "objection": "will it leak?",
        "response_strategy": "show leak-resistant use demo"
      }
    ],
    "operator_review_flags": [
      "need real demo before strong claim"
    ]
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ObjectionHandling",
    "operator_review_required": false,
    "rule_ids_applied": [
      "OBJ-001"
    ],
    "source_anchors_used": [
      "HBR/JTBD family: customer job, context, functional/social/emotional motivation."
    ]
  }
}
```

### ProofRequirement

Purpose: Define what proof is required before a claim, hook, or offer can be used.

Accepted inputs:
- claim
- product_facts
- available_media
- risk_level
- channel

Required outputs:
- proof_required
- proof_available
- proof_gap
- claim_status

Decision rules:
- PRF-001: WHEN claim is factual/product attribute THEN require source data or visual evidence PRIORITY=90
- PRF-002: WHEN claim implies result/performance THEN require stronger proof or reject PRIORITY=95

Rejection rules:
- Reject claim if proof_required is not met.

Anti-generic rules:
- Generic if proof request is only 'add testimonial' without matching claim.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Claim substantiation and risk-control logic.
- Cialdini/influence family: social proof, authority, scarcity, consistency, reciprocity, liking/unity.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `ProofRequirementRule`

Worked example:
```json
{
  "input": {
    "available_media": [
      "photo"
    ],
    "claim": "leak resistant",
    "risk_level": "medium"
  },
  "output": {
    "claim_status": "needs_operator_review",
    "proof_available": [
      "photo"
    ],
    "proof_gap": [
      "video demo"
    ],
    "proof_required": [
      "water/leak demo"
    ]
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ProofRequirement",
    "operator_review_required": false,
    "rule_ids_applied": [
      "PRF-001"
    ],
    "source_anchors_used": [
      "Claim substantiation and risk-control logic."
    ]
  }
}
```

### ClaimRisk

Purpose: Classify and constrain claims before output reaches operator or channel package.

Accepted inputs:
- claim_text
- category
- proof_available
- regulated_risk
- channel

Required outputs:
- risk_level
- claims_allowed
- claims_rejected
- safe_rewrite

Decision rules:
- CLR-001: WHEN claim is absolute/guaranteed/medical THEN reject or require explicit proof and operator review PRIORITY=100
- CLR-002: WHEN claim is attribute-level and proof exists THEN allow with trace PRIORITY=80

Rejection rules:
- Reject medical, guaranteed, impossible, or unprovable claims.

Anti-generic rules:
- Generic if claim risk classification does not cite the exact claim text.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Claim substantiation and risk-control logic.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.
- Channel-specific creative constraint logic.

Conversion target: `ClaimRiskRule`

Worked example:
```json
{
  "input": {
    "category": "pet",
    "claim_text": "never leaks",
    "proof_available": [
      "photo"
    ]
  },
  "output": {
    "claims_allowed": [
      "leak-resistant design"
    ],
    "claims_rejected": [
      "never leaks"
    ],
    "risk_level": "high",
    "safe_rewrite": "designed to help reduce spills"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ClaimRisk",
    "operator_review_required": false,
    "rule_ids_applied": [
      "CLR-001"
    ],
    "source_anchors_used": [
      "Claim substantiation and risk-control logic."
    ]
  }
}
```

### ChannelConstraint

Purpose: Apply channel-specific constraints before hooks/offers are considered usable.

Accepted inputs:
- channel
- creative_format
- claim_risk
- proof_available
- buyer_state

Required outputs:
- format_constraints
- copy_constraints
- proof_constraints
- review_required

Decision rules:
- CHN-001: WHEN channel is Meta and proof is visual THEN prefer visual demo and avoid unsupported before/after claims PRIORITY=80
- CHN-002: WHEN channel proof is weak THEN route risky claim to operator review PRIORITY=85

Rejection rules:
- Reject channel output that requires unavailable asset or prohibited claim.

Anti-generic rules:
- Generic if channel choice does not change format, proof, CTA, or claim limits.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Channel-specific creative constraint logic.
- Claim substantiation and risk-control logic.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `ChannelConstraintRule`

Worked example:
```json
{
  "input": {
    "channel": "Meta",
    "claim_risk": "medium",
    "creative_format": "short video",
    "proof_available": [
      "photo"
    ]
  },
  "output": {
    "copy_constraints": [
      "no absolute claims"
    ],
    "format_constraints": [
      "first-frame visual proof"
    ],
    "review_required": true
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "ChannelConstraint",
    "operator_review_required": false,
    "rule_ids_applied": [
      "CHN-001"
    ],
    "source_anchors_used": [
      "Channel-specific creative constraint logic."
    ]
  }
}
```

### CTA

Purpose: Select a CTA matched to buyer state, friction, channel, and operator constraints.

Accepted inputs:
- buyer_state
- offer
- channel
- friction_level
- proof_status

Required outputs:
- cta_text
- cta_type
- friction_match
- review_required

Decision rules:
- CTA-001: WHEN buyer is problem-aware and proof is adequate THEN use direct product CTA PRIORITY=75
- CTA-002: WHEN proof is incomplete THEN use softer CTA and operator review PRIORITY=85

Rejection rules:
- Reject urgency-only CTA if not supported by offer or inventory reality.

Anti-generic rules:
- Generic if CTA is only buy now without awareness/friction logic.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- Buyer-state/direct-response awareness logic.
- Channel-specific creative constraint logic.
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `CTARule`

Worked example:
```json
{
  "input": {
    "buyer_state": "problem-aware",
    "friction_level": "medium",
    "proof_status": "partial"
  },
  "output": {
    "cta_text": "Revisa si te sirve para tus paseos diarios",
    "cta_type": "soft-direct",
    "friction_match": "medium",
    "review_required": false
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "CTA",
    "operator_review_required": false,
    "rule_ids_applied": [
      "CTA-001"
    ],
    "source_anchors_used": [
      "Buyer-state/direct-response awareness logic."
    ]
  }
}
```

### AntiGenericRejection

Purpose: Provide universal rejection logic against vague, interchangeable marketing output.

Accepted inputs:
- candidate_output
- product_facts_used
- trace
- framework_outputs

Required outputs:
- generic_score
- rejection_reasons
- rewrite_required

Decision rules:
- AGR-001: WHEN output lacks product_facts_used THEN reject as generic PRIORITY=100
- AGR-002: WHEN trace lacks rule ids THEN reject as unauditable PRIORITY=95

Rejection rules:
- Reject any marketing decision with no product facts.
- Reject any marketing decision with no rule trace.

Anti-generic rules:
- Generic if reusable across unrelated products without changing facts, proof, or objection.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.
- Claim substantiation and risk-control logic.
- HBS/STP family: segmentation, target selection, positioning.

Conversion target: `AntiGenericRule`

Worked example:
```json
{
  "input": {
    "candidate_output": "Perfect for everyone who wants convenience",
    "product_facts_used": [],
    "trace": {}
  },
  "output": {
    "generic_score": 0.97,
    "rejection_reasons": [
      "no product facts",
      "no trace"
    ],
    "rewrite_required": true
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "AntiGenericRejection",
    "operator_review_required": false,
    "rule_ids_applied": [
      "AGR-001"
    ],
    "source_anchors_used": [
      "SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend."
    ]
  }
}
```

### DecisionTrace

Purpose: Make every marketing decision auditable by recording rule ids, facts, sources, rejections, and fallback.

Accepted inputs:
- framework_outputs
- rule_applications
- source_anchors
- operator_review_flags

Required outputs:
- decision_trace
- trace_completeness
- audit_warnings

Decision rules:
- TRC-001: WHEN a decision is emitted THEN trace must include framework, rule id, product facts, and source anchor PRIORITY=100
- TRC-002: WHEN fallback is used THEN trace must record fallback_used and reason PRIORITY=95

Rejection rules:
- Reject trace if any emitted decision lacks rule_ids_applied.

Anti-generic rules:
- Generic if trace explains outcome with vague rationale instead of rule ids and facts.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.

Conversion target: `MarketingDecisionTrace`

Worked example:
```json
{
  "input": {
    "framework_outputs": [
      "angle",
      "hook"
    ],
    "rule_applications": [
      "ANG-001",
      "HOK-001"
    ],
    "source_anchors": [
      "JTBD"
    ]
  },
  "output": {
    "audit_warnings": [],
    "decision_trace": {
      "rule_ids_applied": [
        "ANG-001",
        "HOK-001"
      ]
    },
    "trace_completeness": "complete"
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "DecisionTrace",
    "operator_review_required": false,
    "rule_ids_applied": [
      "TRC-001"
    ],
    "source_anchors_used": [
      "SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend."
    ]
  }
}
```

### OperatorReview

Purpose: Define what the operator must review before any external use or future live path.

Accepted inputs:
- claims_rejected
- proof_gaps
- channel_constraints
- spend_status
- live_flags

Required outputs:
- operator_review_notes
- approval_required
- blocked_actions

Decision rules:
- OPR-001: WHEN claim risk or proof gap exists THEN require operator review before package approval PRIORITY=100
- OPR-002: WHEN live flag/spend path is requested THEN block until dedicated guard audit exists PRIORITY=100

Rejection rules:
- Reject automatic external action.
- Reject review note if it does not cite blocked reason.

Anti-generic rules:
- Generic if operator review says only 'check this' without exact risk/proof/action.

Determinism:
- overlap_policy: If multiple rules match, select by tie_break_order and record tie_break_applied.
- fallback_policy: If no safe specific rule matches, reject generic output and route to operator_review_required.

Source anchors:
- SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend.
- Claim substantiation and risk-control logic.
- Channel-specific creative constraint logic.

Conversion target: `OperatorReviewRule`

Worked example:
```json
{
  "input": {
    "claims_rejected": [
      "never leaks"
    ],
    "live_flags": {
      "meta": false
    },
    "proof_gaps": [
      "video demo"
    ]
  },
  "output": {
    "approval_required": true,
    "blocked_actions": [
      "Meta live spend"
    ],
    "operator_review_notes": [
      "Do not use absolute leak claim without proof"
    ]
  },
  "rule_application": [
    "select matching rule by accepted inputs",
    "apply rejection rules before generation",
    "apply deterministic tie_break_order if more than one rule matches",
    "emit output plus trace"
  ],
  "trace": {
    "fallback_used": false,
    "framework": "OperatorReview",
    "operator_review_required": false,
    "rule_ids_applied": [
      "OPR-001"
    ],
    "source_anchors_used": [
      "SYNAPSE internal economics/safety: margin, CAC, proof, operator-en-control, no live spend."
    ]
  }
}
```
