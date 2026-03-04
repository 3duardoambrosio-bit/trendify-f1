from __future__ import annotations

"""
Pipeline E2E: Discovery -> Publish -> Monitor.

Un solo punto de entrada que orquesta el flujo completo:
1) Recibe productos del PipelineOrchestrator
2) Verifica account health
3) Aplica warm-up protocol
4) Construye payload Advantage+
5) Publica via MetaSafeClient (respetando feature flag)
6) Registra resultado (acumula, no revienta)

__MARKER__ embedded in module constant below.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional
import logging
import os

import synapse.meta.safe_client as _meta_safe_client  # noqa: F401
import synapse.discovery.pipeline_orchestrator as _pipeline_orchestrator  # noqa: F401
import synapse.infra.feature_flags as _feature_flags  # noqa: F401

from synapse.meta.account_health import AccountHealthChecker, AccountHealthStatus, AccountMetrics
from synapse.meta.advantage_plus import AdvantagePlusCampaignBuilder
from synapse.meta.warm_up_protocol import WarmUpProtocol

__MARKER__ = "SESSION_S10_pipeline_e2e_20260228"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineE2EConfig:
    enable_health_check: bool = True
    enable_warm_up: bool = True
    enable_publish: bool = True
    enable_creative_gate: bool = True  # S14: validate creatives before publish
    max_products: int = 25

    default_budget_daily_usd: Decimal = Decimal("10")
    daily_cap_usd: Decimal = Decimal("50")

    meta_live_api_flag: str = "meta_live_api"


@dataclass
class PipelineE2EResult:
    products_processed: int
    campaigns_created: int
    campaigns_blocked: int
    errors: List[Dict[str, Any]] = field(default_factory=list)
    health_status: Optional[AccountHealthStatus] = None
    warm_up_limit: Decimal = Decimal("0")
    live_api_enabled: bool = False


def _flag_enabled(flag_name: str) -> bool:
    try:
        if hasattr(_feature_flags, "is_enabled"):
            return bool(_feature_flags.is_enabled(flag_name))
        if hasattr(_feature_flags, "is_feature_enabled"):
            return bool(_feature_flags.is_feature_enabled(flag_name))
        if hasattr(_feature_flags, "enabled"):
            return bool(_feature_flags.enabled(flag_name))
    except Exception as e:
        log.warning("feature_flags lookup failed: %s", e)

    v = os.getenv(flag_name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


class PipelineE2E:
    def __init__(
        self,
        safe_client: Any,
        health_checker: AccountHealthChecker,
        warm_up: WarmUpProtocol,
        advantage_plus: AdvantagePlusCampaignBuilder,
        config: PipelineE2EConfig,
    ):
        self._safe_client = safe_client
        self._health_checker = health_checker
        self._warm_up = warm_up
        self._advantage_plus = advantage_plus
        self._config = config

    def execute(self, products: List[Any], account_metrics: AccountMetrics) -> PipelineE2EResult:
        errors: List[Dict[str, Any]] = []
        created = 0
        blocked = 0

        live = _flag_enabled(self._config.meta_live_api_flag)

        health_status: Optional[AccountHealthStatus] = None
        if self._config.enable_health_check:
            try:
                health_status = self._health_checker.check(account_metrics)
            except Exception as e:
                errors.append({"stage": "health_check", "error": str(e)})
                return PipelineE2EResult(
                    products_processed=0,
                    campaigns_created=0,
                    campaigns_blocked=len(products),
                    errors=errors,
                    health_status=None,
                    warm_up_limit=Decimal("0"),
                    live_api_enabled=live,
                )

            if (health_status.risk_level == "red") or (health_status.can_publish is False):
                return PipelineE2EResult(
                    products_processed=0,
                    campaigns_created=0,
                    campaigns_blocked=len(products),
                    errors=errors,
                    health_status=health_status,
                    warm_up_limit=Decimal("0"),
                    live_api_enabled=live,
                )

        warm_limit = self._config.daily_cap_usd
        if self._config.enable_warm_up:
            try:
                day = self._warm_up.get_current_day()
                warm_limit = self._warm_up.get_daily_limit(day=max(day, 1), daily_cap=self._config.daily_cap_usd)
            except Exception as e:
                errors.append({"stage": "warm_up", "error": str(e)})
                warm_limit = Decimal("0")

        budget_daily = min(self._config.default_budget_daily_usd, warm_limit)

        products_limited = products[: self._config.max_products]
        processed = 0

        for p in products_limited:
            processed += 1
            try:
                product_obj = getattr(p, "product", p)
                creatives = getattr(p, "creatives", getattr(product_obj, "creatives", []))
                pixel_events = getattr(p, "pixel_events", getattr(product_obj, "pixel_events", ["Purchase"]))

                # S14: Creative gate — validate kit BEFORE publishing
                if self._config.enable_creative_gate:
                    kit_dir = getattr(p, "kit_dir", None) or getattr(product_obj, "kit_dir", None)
                    if kit_dir:
                        from synapse.meta.creative_gate_middleware import check_creative_gate
                        gate_check = check_creative_gate(product_obj, kit_dir=kit_dir)
                        if not gate_check.allowed:
                            blocked += 1
                            errors.append({
                                "stage": "creative_gate",
                                "product": getattr(product_obj, "sku", None) or getattr(product_obj, "id", None) or str(product_obj),
                                "reason": gate_check.reason,
                                "gate_errors": gate_check.errors,
                            })
                            continue

                ok, prereq_errors = self._advantage_plus.validate_prerequisites(
                    creatives_count=len(creatives),
                    pixel_events=list(pixel_events),
                    budget_daily=budget_daily,
                )
                if not ok:
                    blocked += 1
                    errors.append(
                        {
                            "stage": "advantage_plus_prereq",
                            "product": getattr(product_obj, "sku", None) or getattr(product_obj, "id", None) or str(product_obj),
                            "error": ",".join(prereq_errors),
                        }
                    )
                    continue

                payload = self._advantage_plus.build_campaign_payload(
                    product=product_obj,
                    budget_daily=budget_daily,
                    creatives=list(creatives),
                )

                if self._config.enable_publish:
                    try:
                        _ = self._safe_client.create_campaign(payload)
                    except Exception as e:
                        blocked += 1
                        errors.append({"stage": "publish", "product": payload.get("product_ref"), "error": str(e)})
                        continue

                created += 1

            except Exception as e:
                blocked += 1
                errors.append({"stage": "pipeline", "error": str(e)})

        return PipelineE2EResult(
            products_processed=processed,
            campaigns_created=created,
            campaigns_blocked=blocked,
            errors=errors,
            health_status=health_status,
            warm_up_limit=warm_limit,
            live_api_enabled=live,
        )