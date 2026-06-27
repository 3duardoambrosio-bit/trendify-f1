# A8-R101 — Marketing Methodology Depth Expansion Spec

RESULT=DRAFT_A8_R101_MARKETING_METHOD_DEPTH_SPEC_READY_FOR_AUDIT

## Scope

- Content/data depth expansion only.
- No code conversion.
- No loader.
- No engine.
- No live Meta/Shopify/Dropi/spend/orders/fulfillment.

## Depth gates
- framework_count: 15
- min_rule_counts: {'AudiencePersona': 5, 'BuyerStateAwareness': 5, 'ProductFactExtraction': 5, 'ValuePropositionPositioning': 5, 'AngleSelection': 8, 'OfferConstruction': 6, 'HookConstruction': 8, 'ObjectionHandling': 6, 'ProofRequirement': 6, 'ClaimRisk': 6, 'ChannelConstraint': 5, 'CTA': 5, 'AntiGenericRejection': 4, 'DecisionTrace': 4, 'OperatorReview': 4}
- per_rule_source_anchor_required: True
- per_rule_trace_fields_required: True
- route_examples_required: ['acceptance', 'rejection', 'fallback']
- global_anti_generic_gates_min: 8
- adversarial_scenarios_min: 8
- no_code_conversion: True
- no_loader: True
- no_engine: True

## Global anti-generic gates
- GLOBAL-AG-001: reject_if=product_facts_used is empty reason=no product-specific grounding
- GLOBAL-AG-002: reject_if=rule_ids_applied is empty reason=unauditable decision
- GLOBAL-AG-003: reject_if=source_anchor is missing reason=no source/principle grounding
- GLOBAL-AG-004: reject_if=angle only uses category while product facts exist reason=category-only angle
- GLOBAL-AG-005: reject_if=hook works after swapping product noun reason=interchangeable hook
- GLOBAL-AG-006: reject_if=offer does not answer a segment objection reason=generic offer
- GLOBAL-AG-007: reject_if=claim lacks proof requirement/status reason=unsupported claim
- GLOBAL-AG-008: reject_if=CTA ignores buyer_state/channel/friction reason=generic CTA

## Adversarial scenarios
- ADV-001: poor_product_data -> ['fallback', 'operator_review_required']
- ADV-002: insufficient_proof -> ['proof_gap', 'lower_claim_or_reject']
- ADV-003: risky_claim -> ['claim_rejected', 'safe_rewrite']
- ADV-004: tight_margin_discount_offer -> ['reject_discount_offer', 'operator_review_required']
- ADV-005: competing_rules -> ['tie_break_applied']
- ADV-006: meta_weak_proof -> ['channel_constraint', 'operator_review_required']
- ADV-007: pretty_but_generic_hook -> ['generic_rejected']
- ADV-008: cold_buyer_aggressive_cta -> ['cta_softened_or_rejected']

## Framework depth

### AudiencePersona

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: AudienceRule

Decision rules:
- AUD-D001 [JTBD] priority=99 WHEN product facts reveal a concrete use case THEN select persona by job/use-case instead of demographic stereotype
- AUD-D002 [SYNAPSE] priority=98 WHEN CAC or margin requires efficient acquisition THEN prefer high-intent segment with low education burden
- AUD-D003 [STP] priority=97 WHEN buyer friction is visible in product context THEN select persona around friction to remove
- AUD-D004 [JTBD] priority=96 WHEN product is used in a recurring occasion THEN target the occasion and trigger context
- AUD-D005 [SYNAPSE] priority=95 WHEN segment lacks proof or purchase context THEN reject broad audience and route operator review

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'select persona by job/use-case instead of demographic stereotype', 'operator_review_required': False} trace={'framework': 'AudiencePersona', 'rule_id': 'AUD-D001', 'source_anchor': 'JTBD'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'AudiencePersona', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'AudiencePersona', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### BuyerStateAwareness

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: BuyerStateRule

Decision rules:
- BSA-D001 [AWARENESS] priority=99 WHEN buyer knows the problem THEN use direct problem-solution framing
- BSA-D002 [AWARENESS] priority=98 WHEN buyer knows solutions but not this SKU THEN show differentiating mechanism and proof
- BSA-D003 [AWARENESS] priority=97 WHEN problem is not explicit THEN use situation-first hook and soft CTA
- BSA-D004 [CLAIMS] priority=96 WHEN claim risk or category distrust is high THEN increase proof depth and lower claim intensity
- BSA-D005 [DIRECT_RESPONSE] priority=95 WHEN use case is time/friction sensitive THEN use friction-removal offer and direct CTA if proof allows

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'use direct problem-solution framing', 'operator_review_required': False} trace={'framework': 'BuyerStateAwareness', 'rule_id': 'BSA-D001', 'source_anchor': 'AWARENESS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'BuyerStateAwareness', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'BuyerStateAwareness', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ProductFactExtraction

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: ProductFactRule

Decision rules:
- PFX-D001 [CLAIMS] priority=99 WHEN attribute appears in source data THEN allow as product_facts_used
- PFX-D002 [CLAIMS] priority=98 WHEN benefit is inferred from attributes THEN mark as hypothesis and require proof
- PFX-D003 [PERSUASION] priority=97 WHEN media demonstrates an attribute THEN allow stronger visual hook with trace
- PFX-D004 [CLAIMS] priority=96 WHEN claim lacks evidence THEN reject or operator-review the claim
- PFX-D005 [SYNAPSE] priority=95 WHEN margin/CAC affects offer THEN include economics in offer constraints

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'allow as product_facts_used', 'operator_review_required': False} trace={'framework': 'ProductFactExtraction', 'rule_id': 'PFX-D001', 'source_anchor': 'CLAIMS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ProductFactExtraction', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ProductFactExtraction', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ValuePropositionPositioning

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: PositioningRule

Decision rules:
- POS-D001 [JTBD] priority=99 WHEN job-to-be-done is concrete THEN position around job completion
- POS-D002 [STP] priority=98 WHEN known alternative is bulky/slow/risky THEN position against tradeoff using product fact
- POS-D003 [DIRECT_RESPONSE] priority=97 WHEN price is not lowest THEN position around proof/value not cheapness
- POS-D004 [CLAIMS] priority=96 WHEN claim risk is medium/high THEN position with safe mechanism and proof requirement
- POS-D005 [SYNAPSE] priority=95 WHEN positioning is category-only THEN reject as generic

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'position around job completion', 'operator_review_required': False} trace={'framework': 'ValuePropositionPositioning', 'rule_id': 'POS-D001', 'source_anchor': 'JTBD'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ValuePropositionPositioning', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ValuePropositionPositioning', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### AngleSelection

- min_rule_count: 8
- actual_rule_count: 8
- conversion_target: AngleRule

Decision rules:
- ANG-D001 [PERSUASION] priority=99 WHEN specific use-case fact and demo proof exist THEN select demonstration/use-case angle
- ANG-D002 [CLAIMS] priority=98 WHEN proof is weak or claim risk high THEN select low-claim situational angle
- ANG-D003 [DIRECT_RESPONSE] priority=97 WHEN dominant objection is concrete THEN select angle that resolves objection
- ANG-D004 [CLAIMS] priority=96 WHEN transformation proof is absent THEN frame current friction not guaranteed after-state
- ANG-D005 [SYNAPSE] priority=95 WHEN CAC/margin tight THEN select high-intent/direct angle
- ANG-D006 [PERSUASION] priority=94 WHEN safe proof/social evidence exists THEN select proof-led angle
- ANG-D007 [CHANNEL] priority=93 WHEN channel format has first-frame constraint THEN select visual-first angle
- ANG-D008 [SYNAPSE] priority=92 WHEN specific product fact exists THEN reject category-only angle

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'select demonstration/use-case angle', 'operator_review_required': False} trace={'framework': 'AngleSelection', 'rule_id': 'ANG-D001', 'source_anchor': 'PERSUASION'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'AngleSelection', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'AngleSelection', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### OfferConstruction

- min_rule_count: 6
- actual_rule_count: 6
- conversion_target: OfferRule

Decision rules:
- OFF-D001 [DIRECT_RESPONSE] priority=99 WHEN objection is convenience/friction THEN promise friction reduction via product fact
- OFF-D002 [SYNAPSE] priority=98 WHEN margin is tight THEN avoid discount-dependent offer
- OFF-D003 [CLAIMS] priority=97 WHEN proof is partial THEN soften offer claim and require operator review
- OFF-D004 [SYNAPSE] priority=96 WHEN AOV target needs lift THEN suggest value bundle only if margin allows
- OFF-D005 [PERSUASION] priority=95 WHEN buyer distrust visible THEN add safe risk-reversal language requiring operator review
- OFF-D006 [CLAIMS] priority=94 WHEN urgency lacks real basis THEN reject scarcity/limited-time offer

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'promise friction reduction via product fact', 'operator_review_required': False} trace={'framework': 'OfferConstruction', 'rule_id': 'OFF-D001', 'source_anchor': 'DIRECT_RESPONSE'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'OfferConstruction', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'OfferConstruction', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### HookConstruction

- min_rule_count: 8
- actual_rule_count: 8
- conversion_target: HookRule

Decision rules:
- HOK-D001 [CHANNEL] priority=99 WHEN demo proof exists THEN make proof visible in first frame/line
- HOK-D002 [DIRECT_RESPONSE] priority=98 WHEN objection is concrete THEN answer objection without overclaiming
- HOK-D003 [AWARENESS] priority=97 WHEN buyer state is latent THEN lead with recognizable situation
- HOK-D004 [JTBD] priority=96 WHEN mechanism is concrete THEN name mechanism and show product fact
- HOK-D005 [CLAIMS] priority=95 WHEN proof is incomplete THEN avoid strong claim and ask lower-risk curiosity
- HOK-D006 [SYNAPSE] priority=94 WHEN price requires value defense THEN hook around avoided friction/cost/time
- HOK-D007 [CHANNEL] priority=93 WHEN Meta short video format THEN force first-frame visual contrast
- HOK-D008 [SYNAPSE] priority=92 WHEN hook works after swapping product noun THEN reject as generic

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'make proof visible in first frame/line', 'operator_review_required': False} trace={'framework': 'HookConstruction', 'rule_id': 'HOK-D001', 'source_anchor': 'CHANNEL'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'HookConstruction', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'HookConstruction', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ObjectionHandling

- min_rule_count: 6
- actual_rule_count: 6
- conversion_target: ObjectionRule

Decision rules:
- OBJ-D001 [CLAIMS] priority=99 WHEN quality objection appears THEN require demo/detail proof before claim
- OBJ-D002 [DIRECT_RESPONSE] priority=98 WHEN price objection appears THEN answer with job/value tradeoff
- OBJ-D003 [JTBD] priority=97 WHEN buyer may doubt it fits their use case THEN map use-case proof to segment
- OBJ-D004 [PERSUASION] priority=96 WHEN seller/category trust is weak THEN increase proof/review/operator review
- OBJ-D005 [SYNAPSE] priority=95 WHEN delivery friction is relevant THEN route to operator if fulfillment proof missing
- OBJ-D006 [SYNAPSE] priority=94 WHEN objection list is only price/trust THEN reject unless tied to product/segment

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'require demo/detail proof before claim', 'operator_review_required': False} trace={'framework': 'ObjectionHandling', 'rule_id': 'OBJ-D001', 'source_anchor': 'CLAIMS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ObjectionHandling', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ObjectionHandling', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ProofRequirement

- min_rule_count: 6
- actual_rule_count: 6
- conversion_target: ProofRequirementRule

Decision rules:
- PRF-D001 [CLAIMS] priority=99 WHEN claim is factual attribute THEN require source data or visual evidence
- PRF-D002 [CLAIMS] priority=98 WHEN claim implies result/performance THEN require stronger proof or reject
- PRF-D003 [PERSUASION] priority=97 WHEN social proof is cited THEN require source and scope
- PRF-D004 [CHANNEL] priority=96 WHEN hook depends on visual mechanism THEN require media asset
- PRF-D005 [SYNAPSE] priority=95 WHEN offer implies savings/value THEN require price/margin trace
- PRF-D006 [SYNAPSE] priority=94 WHEN proof missing THEN route to lower-claim wording or operator review

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'require source data or visual evidence', 'operator_review_required': False} trace={'framework': 'ProofRequirement', 'rule_id': 'PRF-D001', 'source_anchor': 'CLAIMS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ProofRequirement', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ProofRequirement', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ClaimRisk

- min_rule_count: 6
- actual_rule_count: 6
- conversion_target: ClaimRiskRule

Decision rules:
- CLR-D001 [CLAIMS] priority=99 WHEN claim is absolute/guaranteed THEN reject or require extraordinary proof
- CLR-D002 [CLAIMS] priority=98 WHEN claim is attribute-level and proof exists THEN allow with trace
- CLR-D003 [CLAIMS] priority=97 WHEN claim touches medical/safety outcome THEN reject or operator review
- CLR-D004 [CLAIMS] priority=96 WHEN claim compares against alternatives THEN require explicit comparison proof
- CLR-D005 [SYNAPSE] priority=95 WHEN claim risk high but value can be stated safely THEN emit safe_rewrite
- CLR-D006 [CHANNEL] priority=94 WHEN channel constraints disallow claim style THEN reject for channel package

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'reject or require extraordinary proof', 'operator_review_required': False} trace={'framework': 'ClaimRisk', 'rule_id': 'CLR-D001', 'source_anchor': 'CLAIMS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ClaimRisk', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ClaimRisk', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### ChannelConstraint

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: ChannelConstraintRule

Decision rules:
- CHN-D001 [CHANNEL] priority=99 WHEN channel is Meta and proof is visual THEN prefer first-frame visual demo
- CHN-D002 [CLAIMS] priority=98 WHEN proof weak on visual channel THEN route risky claim to operator review
- CHN-D003 [CHANNEL] priority=97 WHEN format is short creative THEN limit hook to one product fact plus one friction
- CHN-D004 [CLAIMS] priority=96 WHEN ad claim not supported by destination THEN reject or require rewrite
- CHN-D005 [SYNAPSE] priority=95 WHEN live/spend path requested THEN block until guard audit

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'prefer first-frame visual demo', 'operator_review_required': False} trace={'framework': 'ChannelConstraint', 'rule_id': 'CHN-D001', 'source_anchor': 'CHANNEL'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'ChannelConstraint', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'ChannelConstraint', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### CTA

- min_rule_count: 5
- actual_rule_count: 5
- conversion_target: CTARule

Decision rules:
- CTA-D001 [AWARENESS] priority=99 WHEN problem-aware and proof adequate THEN use direct product CTA
- CTA-D002 [CLAIMS] priority=98 WHEN proof incomplete or buyer cold THEN use softer evaluation CTA
- CTA-D003 [JTBD] priority=97 WHEN buyer friction concrete THEN CTA references friction solved
- CTA-D004 [CHANNEL] priority=96 WHEN channel requires low-friction click THEN match CTA to channel format
- CTA-D005 [CLAIMS] priority=95 WHEN urgency lacks basis THEN reject urgency-only CTA

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'use direct product CTA', 'operator_review_required': False} trace={'framework': 'CTA', 'rule_id': 'CTA-D001', 'source_anchor': 'AWARENESS'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'CTA', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'CTA', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### AntiGenericRejection

- min_rule_count: 4
- actual_rule_count: 4
- conversion_target: AntiGenericRule

Decision rules:
- AGR-D001 [SYNAPSE] priority=99 WHEN output lacks product_facts_used THEN reject as generic
- AGR-D002 [SYNAPSE] priority=98 WHEN trace lacks rule ids THEN reject as unauditable
- AGR-D003 [STP] priority=97 WHEN output works after swapping product noun THEN reject as interchangeable
- AGR-D004 [SYNAPSE] priority=96 WHEN angle/offer/hook only uses category THEN reject if product fact exists

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'reject as generic', 'operator_review_required': False} trace={'framework': 'AntiGenericRejection', 'rule_id': 'AGR-D001', 'source_anchor': 'SYNAPSE'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'AntiGenericRejection', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'AntiGenericRejection', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### DecisionTrace

- min_rule_count: 4
- actual_rule_count: 4
- conversion_target: MarketingDecisionTrace

Decision rules:
- TRC-D001 [SYNAPSE] priority=99 WHEN decision emitted THEN trace framework/rule/facts/source
- TRC-D002 [SYNAPSE] priority=98 WHEN fallback used THEN record fallback reason
- TRC-D003 [SYNAPSE] priority=97 WHEN rule rejects output THEN record rejection reason and blocked field
- TRC-D004 [SYNAPSE] priority=96 WHEN source anchor used THEN record source_anchor per rule

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'trace framework/rule/facts/source', 'operator_review_required': False} trace={'framework': 'DecisionTrace', 'rule_id': 'TRC-D001', 'source_anchor': 'SYNAPSE'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'DecisionTrace', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'DecisionTrace', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}

### OperatorReview

- min_rule_count: 4
- actual_rule_count: 4
- conversion_target: OperatorReviewRule

Decision rules:
- OPR-D001 [SYNAPSE] priority=99 WHEN claim risk or proof gap exists THEN require operator review
- OPR-D002 [SYNAPSE] priority=98 WHEN live flag/spend requested THEN block until guard audit
- OPR-D003 [SYNAPSE] priority=97 WHEN offer may break margin guard THEN require operator review
- OPR-D004 [CHANNEL] priority=96 WHEN creative requires missing proof/asset THEN require operator review

Route examples:
- acceptance: expected={'status': 'accepted', 'decision': 'require operator review', 'operator_review_required': False} trace={'framework': 'OperatorReview', 'rule_id': 'OPR-D001', 'source_anchor': 'SYNAPSE'}
- rejection: expected={'status': 'rejected', 'reason': 'generic_or_unauditable', 'operator_review_required': True} trace={'framework': 'OperatorReview', 'rejection_signal': 'GENERIC_REJECTED'}
- fallback: expected={'status': 'fallback', 'decision': 'operator_review_required', 'operator_review_required': True} trace={'framework': 'OperatorReview', 'fallback_used': True, 'fallback_reason': 'insufficient_specificity_or_proof'}
