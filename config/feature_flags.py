from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping

_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off"}
_LIVE_FLAG_NAMES = {
    "meta_live",
    "meta_live_api",
    "live_meta",
    "shopify_live",
    "shopify_live_api",
    "live_shopify",
    "dropi_live",
    "dropi_live_api",
    "dropi_live_orders",
    "live_dropi",
    "spend_real_money",
    "spend_real_money_api",
    "spend_real",
}


def _normalize(name: str | None) -> str:
    return (name or "").strip().lower()


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    value = (raw or "").strip().lower()
    if value == "":
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def _env_first(*names: str, default: bool) -> bool:
    for name in names:
        if name in os.environ:
            return _parse_bool(os.getenv(name), default=default)
    return default


@dataclass(frozen=True, slots=True, init=False)
class FeatureFlags:
    """
    Single canonical FeatureFlags implementation.

    Supports all active contracts in the repo:

    1) config.feature_flags
       - meta_live / shopify_live / dropi_live / spend_real_money

    2) infra.feature_flags
       - dry_run / live_meta / live_shopify / live_dropi
       - from_env()
       - allow_network()

    3) synapse.infra.feature_flags
       - values={}
       - load()
       - is_on()
    """

    meta_live: bool
    shopify_live: bool
    dropi_live: bool
    spend_real_money: bool
    dry_run: bool
    values: Dict[str, bool]

    def __init__(
        self,
        *,
        meta_live: bool | None = None,
        shopify_live: bool | None = None,
        dropi_live: bool | None = None,
        spend_real_money: bool | None = None,
        dry_run: bool | None = None,
        values: Mapping[str, bool] | None = None,

        # config aliases
        meta_live_api: bool | None = None,
        shopify_live_api: bool | None = None,
        dropi_live_api: bool | None = None,
        dropi_live_orders: bool | None = None,
        spend_real_money_api: bool | None = None,
        spend_real: bool | None = None,

        # infra aliases
        live_meta: bool | None = None,
        live_shopify: bool | None = None,
        live_dropi: bool | None = None,

        **kwargs: Any,
    ) -> None:
        if kwargs:
            raise TypeError(f"Unexpected keyword arguments: {', '.join(sorted(kwargs.keys()))}")

        raw_values: Dict[str, bool] = {}
        if values:
            for key, value in values.items():
                raw_values[_normalize(str(key))] = bool(value)

        def _value_override(*names: str) -> bool | None:
            for name in names:
                normalized = _normalize(name)
                if normalized in raw_values:
                    return raw_values[normalized]
            return None

        if meta_live is None:
            meta_live = meta_live_api
        if meta_live is None:
            meta_live = live_meta
        if meta_live is None:
            meta_live = _value_override("meta_live", "meta_live_api", "live_meta")

        if shopify_live is None:
            shopify_live = shopify_live_api
        if shopify_live is None:
            shopify_live = live_shopify
        if shopify_live is None:
            shopify_live = _value_override("shopify_live", "shopify_live_api", "live_shopify")

        if dropi_live is None:
            dropi_live = dropi_live_api
        if dropi_live is None:
            dropi_live = dropi_live_orders
        if dropi_live is None:
            dropi_live = live_dropi
        if dropi_live is None:
            dropi_live = _value_override("dropi_live", "dropi_live_api", "dropi_live_orders", "live_dropi")

        if spend_real_money is None:
            spend_real_money = spend_real_money_api
        if spend_real_money is None:
            spend_real_money = spend_real
        if spend_real_money is None:
            spend_real_money = _value_override("spend_real_money", "spend_real_money_api", "spend_real")

        if dry_run is None:
            dry_run = _value_override("dry_run")

        object.__setattr__(
            self,
            "meta_live",
            _env_first("SYNAPSE_META_LIVE", "SYNAPSE_LIVE_META", default=False)
            if meta_live is None else bool(meta_live),
        )
        object.__setattr__(
            self,
            "shopify_live",
            _env_first("SYNAPSE_SHOPIFY_LIVE", "SYNAPSE_LIVE_SHOPIFY", default=False)
            if shopify_live is None else bool(shopify_live),
        )
        object.__setattr__(
            self,
            "dropi_live",
            _env_first("SYNAPSE_DROPI_LIVE", "SYNAPSE_LIVE_DROPI", default=False)
            if dropi_live is None else bool(dropi_live),
        )
        object.__setattr__(
            self,
            "spend_real_money",
            _env_first("SYNAPSE_SPEND_REAL_MONEY", default=False)
            if spend_real_money is None else bool(spend_real_money),
        )
        object.__setattr__(
            self,
            "dry_run",
            _env_first("SYNAPSE_DRY_RUN", default=True)
            if dry_run is None else bool(dry_run),
        )

        merged = dict(raw_values)
        merged.update(
            {
                "meta_live": self.meta_live,
                "meta_live_api": self.meta_live,
                "live_meta": self.meta_live,
                "shopify_live": self.shopify_live,
                "shopify_live_api": self.shopify_live,
                "live_shopify": self.shopify_live,
                "dropi_live": self.dropi_live,
                "dropi_live_api": self.dropi_live,
                "dropi_live_orders": self.dropi_live,
                "live_dropi": self.dropi_live,
                "spend_real_money": self.spend_real_money,
                "spend_real_money_api": self.spend_real_money,
                "spend_real": self.spend_real_money,
                "dry_run": self.dry_run,
            }
        )
        object.__setattr__(self, "values", merged)

    @staticmethod
    def from_env() -> "FeatureFlags":
        def env_bool(*names: str, default: bool = False) -> bool:
            saw_explicit_false = False
            for env_name in names:
                raw = os.getenv(env_name)
                if raw is None or raw.strip() == "":
                    continue

                parsed = _parse_bool(raw, default=default)
                if parsed is True:
                    return True

                saw_explicit_false = True

            if saw_explicit_false:
                return False
            return default

        meta_live = env_bool("SYNAPSE_META_LIVE", "SYNAPSE_LIVE_META", default=False)
        shopify_live = env_bool("SYNAPSE_SHOPIFY_LIVE", "SYNAPSE_LIVE_SHOPIFY", default=False)
        dropi_live = env_bool("SYNAPSE_DROPI_LIVE", "SYNAPSE_LIVE_DROPI", default=False)
        spend_real_money = env_bool(
            "SYNAPSE_SPEND_REAL_MONEY",
            "SYNAPSE_SPEND_REAL",
            "SYNAPSE_REAL_SPEND",
            default=False,
        )
        dry_run = env_bool("SYNAPSE_DRY_RUN", default=True)

        return FeatureFlags(
            meta_live=meta_live,
            shopify_live=shopify_live,
            dropi_live=dropi_live,
            spend_real_money=spend_real_money,
            dry_run=dry_run,
            values={
                "meta_live": meta_live,
                "live_meta": meta_live,
                "meta_live_api": meta_live,
                "shopify_live": shopify_live,
                "live_shopify": shopify_live,
                "shopify_live_api": shopify_live,
                "dropi_live": dropi_live,
                "live_dropi": dropi_live,
                "dropi_live_api": dropi_live,
                "dropi_live_orders": dropi_live,
                "spend_real_money": spend_real_money,
                "spend_real": spend_real_money,
                "spend_real_money_api": spend_real_money,
                "dry_run": dry_run,
            },
        )
    @staticmethod
    def load(prefix: str = "SYNAPSE_FLAG_") -> "FeatureFlags":
        loaded: dict[str, bool] = {}
        for env_name, env_value in os.environ.items():
            if env_name.startswith(prefix):
                name = _normalize(env_name[len(prefix):])
                if prefix == "SYNAPSE_FLAG_" and name in _LIVE_FLAG_NAMES:
                    continue
                loaded[name] = _parse_bool(env_value, default=False)
        return FeatureFlags(values=loaded)
    def is_on(self, name: str, default: bool = False) -> bool:
        normalized = _normalize(name)
        if normalized == "":
            return default
        return self.values.get(normalized, default)

    def as_dict(self) -> Dict[str, bool]:
        return {
            "dry_run": self.dry_run,
            "live_meta": self.live_meta,
            "live_shopify": self.live_shopify,
            "live_dropi": self.live_dropi,
            "meta_live": self.meta_live,
            "shopify_live": self.shopify_live,
            "dropi_live": self.dropi_live,
            "spend_real_money": self.spend_real_money,
        }

    def allow_network(self, system: str) -> bool:
        normalized = _normalize(system)
        if self.dry_run:
            return False
        if normalized == "meta":
            return self.live_meta
        if normalized == "shopify":
            return self.live_shopify
        if normalized == "dropi":
            return self.live_dropi
        return False

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

    @property
    def live_meta(self) -> bool:
        return self.meta_live

    @property
    def live_shopify(self) -> bool:
        return self.shopify_live

    @property
    def live_dropi(self) -> bool:
        return self.dropi_live


FLAGS = FeatureFlags()

__all__ = ["FeatureFlags", "FLAGS", "_parse_bool"]
