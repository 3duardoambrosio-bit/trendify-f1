from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


__MARKER__ = "SECRETS_CONTRACT_2026-01-15_V1"


@dataclass(frozen=True)
class SecretSpec:
    key: str
    required: bool = True
    notes: str = ""


@dataclass(frozen=True)
class ConnectorSpec:
    name: str
    required: List[SecretSpec]
    optional: List[SecretSpec]


def contract() -> Dict[str, ConnectorSpec]:
    """
    Central truth: qué secrets existen y cuáles son required por conector.
    Esto NO guarda secretos. Solo define el contrato.
    """
    meta_required = [
        SecretSpec("META_AD_ACCOUNT_ID", True, "Ad account numeric id (sin act_)"),
        SecretSpec("META_ACCESS_TOKEN", True, "User/System access token con permisos Ads"),
        SecretSpec("META_PAGE_ID", True, "Page id para creativos"),
        SecretSpec("META_IG_ACTOR_ID", True, "Instagram actor id"),
    ]
    meta_optional = [
        SecretSpec("META_APP_ID", False, "App id (útil para debug_token)"),
        SecretSpec("META_APP_SECRET", False, "App secret (útil para debug_token)"),
        SecretSpec("META_PIXEL_ID", False, "Pixel id si trackeas conversiones"),
        SecretSpec("META_GRAPH_VERSION", False, "Ej: v22.0"),
    ]

    shopify_required = [
        SecretSpec("SHOPIFY_SHOP", True, "tu tienda: midominio.myshopify.com o dominio"),
        SecretSpec("SHOPIFY_ACCESS_TOKEN", True, "Admin API access token (Custom App)"),
    ]
    shopify_optional = [
        SecretSpec("SHOPIFY_API_VERSION", False, "Ej: 2024-07"),
    ]

    google_required = [
        SecretSpec("GOOGLE_CLIENT_ID", True, "OAuth client id"),
        SecretSpec("GOOGLE_CLIENT_SECRET", True, "OAuth client secret"),
        SecretSpec("GOOGLE_REFRESH_TOKEN", True, "Refresh token (para no reloguear)"),
    ]
    google_optional = [
        SecretSpec("GOOGLE_ADS_DEVELOPER_TOKEN", False, "Si usas Google Ads API"),
        SecretSpec("GOOGLE_MCC_ID", False, "Manager account id si aplica"),
    ]

    return {
        "meta": ConnectorSpec("meta", required=meta_required, optional=meta_optional),
        "shopify": ConnectorSpec("shopify", required=shopify_required, optional=shopify_optional),
        "google": ConnectorSpec("google", required=google_required, optional=google_optional),
    }


def scopes() -> List[str]:
    return list(contract().keys())