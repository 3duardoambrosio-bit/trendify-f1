from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_TRUE = {"1", "true", "yes", "y", "on"}


def _env_flag(name: str) -> bool:
    v = os.getenv(name, "")
    if v is None:
        return False
    return v.strip().lower() in _TRUE


@dataclass(frozen=True, slots=True, init=False)
class FeatureFlags:
    """
    Canonical flags:
      - meta_live
      - shopify_live
      - dropi_live
      - spend_real_money

    Compatibility aliases accepted (tests/legacy):
      - meta_live_api
      - shopify_live_api
      - dropi_live_api
      - dropi_live_orders   (maps -> dropi_live)
      - spend_real_money_api
      - spend_real
    """

    meta_live: bool
    shopify_live: bool
    dropi_live: bool
    spend_real_money: bool

    def __init__(
        self,
        *,
        meta_live: bool | None = None,
        shopify_live: bool | None = None,
        dropi_live: bool | None = None,
        spend_real_money: bool | None = None,

        # compat aliases (legacy tests/clients)
        meta_live_api: bool | None = None,
        shopify_live_api: bool | None = None,
        dropi_live_api: bool | None = None,

        # NEW: alias usado por tests actuales
        dropi_live_orders: bool | None = None,

        spend_real_money_api: bool | None = None,
        spend_real: bool | None = None,

        # strict: si llega algo desconocido, revienta (no ocultamos bugs)
        **kwargs: Any,
    ) -> None:
        if kwargs:
            raise TypeError(f"Unexpected keyword arguments: {', '.join(sorted(kwargs.keys()))}")

        # map aliases -> canonical
        if meta_live is None and meta_live_api is not None:
            meta_live = meta_live_api

        if shopify_live is None and shopify_live_api is not None:
            shopify_live = shopify_live_api

        if dropi_live is None:
            if dropi_live_api is not None:
                dropi_live = dropi_live_api
            elif dropi_live_orders is not None:
                dropi_live = dropi_live_orders

        if spend_real_money is None:
            if spend_real_money_api is not None:
                spend_real_money = spend_real_money_api
            elif spend_real is not None:
                spend_real_money = spend_real

        object.__setattr__(self, "meta_live", _env_flag("SYNAPSE_META_LIVE") if meta_live is None else bool(meta_live))
        object.__setattr__(self, "shopify_live", _env_flag("SYNAPSE_SHOPIFY_LIVE") if shopify_live is None else bool(shopify_live))
        object.__setattr__(self, "dropi_live", _env_flag("SYNAPSE_DROPI_LIVE") if dropi_live is None else bool(dropi_live))
        object.__setattr__(self, "spend_real_money", _env_flag("SYNAPSE_SPEND_REAL_MONEY") if spend_real_money is None else bool(spend_real_money))

    # alias properties for compatibility
    @property
    def meta_live_api(self) -> bool:
        return self.meta_live

    @property
    def shopify_live_api(self) -> bool:
        return self.shopify_live

    @property
    def dropi_live_api(self) -> bool:
        return self.dropi_live

    @property
    def dropi_live_orders(self) -> bool:
        return self.dropi_live

    @property
    def spend_real_money_api(self) -> bool:
        return self.spend_real_money

    @property
    def spend_real(self) -> bool:
        return self.spend_real_money


FLAGS = FeatureFlags()