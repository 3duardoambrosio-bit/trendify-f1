from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ShopifyConfig:
    enabled: bool
    shop_domain: str
    access_token: str


@dataclass(frozen=True)
class DropiConfig:
    enabled: bool
    api_base: str
    api_key: str


@dataclass(frozen=True)
class MetaConfig:
    enabled: bool
    pixel_id: str
    access_token: str


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() in {"1", "true", "TRUE", "yes", "YES"}


def load_shopify_config() -> ShopifyConfig:
    return ShopifyConfig(
        enabled=_env_bool("SYNAPSE_SHOPIFY_ENABLED", "0"),
        shop_domain=os.getenv("SYNAPSE_SHOPIFY_SHOP_DOMAIN", "").strip(),
        access_token=os.getenv("SYNAPSE_SHOPIFY_ACCESS_TOKEN", "").strip(),
    )


def load_dropi_config() -> DropiConfig:
    return DropiConfig(
        enabled=_env_bool("SYNAPSE_DROPI_ENABLED", "0"),
        api_base=os.getenv("SYNAPSE_DROPI_API_BASE", "").strip(),
        api_key=os.getenv("SYNAPSE_DROPI_API_KEY", "").strip(),
    )


def load_meta_config() -> MetaConfig:
    return MetaConfig(
        enabled=_env_bool("SYNAPSE_META_ENABLED", "0"),
        pixel_id=os.getenv("SYNAPSE_META_PIXEL_ID", "").strip(),
        access_token=os.getenv("SYNAPSE_META_ACCESS_TOKEN", "").strip(),
    )