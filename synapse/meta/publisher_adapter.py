"""Adapter wrapping the existing Meta publisher for safe_client use. S7."""
from __future__ import annotations

from synapse.meta.graph_version import resolve_meta_graph_version

import json
import os
from collections.abc import Mapping
from typing import Any, Dict
from urllib.parse import urlencode

from synapse.integrations.http_client import (
    HttpClientError,
    HttpRequest,
    HttpResponseError,
    HttpTimeoutError,
    SimpleHttpClient,
)
from synapse.infra.feature_flags import FeatureFlags
from synapse.meta.publisher_contracts import MetaCampaignPayload, MetaPauseRequest, reject_forbidden_meta_api_keys

_GRAPH_BASE_URL = "https://graph.facebook.com"
_DEFAULT_TIMEOUT_S = 60.0


def _campaign_payload_to_api_dict(payload: MetaCampaignPayload | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, MetaCampaignPayload):
        return payload.to_api_dict()

    api_payload = dict(payload)
    reject_forbidden_meta_api_keys(api_payload, context="Meta campaign mapping payload")
    return api_payload


def _pause_request_to_api_dict(request: MetaPauseRequest | str) -> Dict[str, Any]:
    if isinstance(request, MetaPauseRequest):
        return request.to_api_dict()
    return {"campaign_id": str(request), "status": "PAUSED"}


def _require_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise RuntimeError(f"Missing required Meta live secret/env: {name}")
    return value


def _graph_version() -> str:
    return str(resolve_meta_graph_version()).strip()


def _timeout_s() -> float:
    raw = str(os.getenv("META_TIMEOUT_S", "")).strip()
    if not raw:
        return _DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_S
    return value if value > 0 else _DEFAULT_TIMEOUT_S


def _normalize_ad_account_id(value: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise RuntimeError("META_AD_ACCOUNT_ID is empty")
    return cleaned if cleaned.startswith("act_") else f"act_{cleaned}"


def _build_http_client() -> SimpleHttpClient:
    # Retry/circuit-breaker viven en safe_client.
    # Este adapter solo hace el transport mínimo.
    return SimpleHttpClient(
        retry_max=0,
        backoff_s=0.0,
        dry_run=False,
        user_agent="synapse-meta-publisher/1.0",
    )


def _encode_form_fields(fields: Mapping[str, Any]) -> bytes:
    encoded: Dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            encoded[str(key)] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            encoded[str(key)] = "true" if value else "false"
        else:
            encoded[str(key)] = str(value)
    return urlencode(encoded).encode("utf-8")


def _decode_response_body(body: bytes) -> Dict[str, Any]:
    if not body:
        return {}
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
    if isinstance(data, dict):
        return data
    return {"data": data}


def _post_form(url: str, fields: Mapping[str, Any]) -> Dict[str, Any]:
    client = _build_http_client()
    request = HttpRequest(
        method="POST",
        url=url,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        body=_encode_form_fields(fields),
        timeout_s=_timeout_s(),
    )

    try:
        response = client.request(request)
    except HttpResponseError as exc:
        body = _decode_response_body(exc.body)
        raise RuntimeError(
            "Meta Graph API rejected request "
            f"(status={exc.status}, body={json.dumps(body, ensure_ascii=False, sort_keys=True)})"
        ) from exc
    except HttpTimeoutError as exc:
        raise RuntimeError("Meta Graph API timeout") from exc
    except HttpClientError as exc:
        raise RuntimeError(f"Meta Graph API transport failure: {exc}") from exc

    return _decode_response_body(response.body)


def _campaign_endpoint(ad_account_id: str) -> str:
    return f"{_GRAPH_BASE_URL}/{_graph_version()}/{ad_account_id}/campaigns"


def _pause_endpoint(campaign_id: str) -> str:
    return f"{_GRAPH_BASE_URL}/{_graph_version()}/{campaign_id}"


def _parse_live_api_flag(raw: str) -> bool:
    value = str(raw).strip().lower()
    if not value:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return False


def _is_live_transport_enabled() -> bool:
    # Gate explícito del adapter.
    # Mantiene compat legacy: OFF por default.
    raw_api_flag = os.getenv("SYNAPSE_FLAG_META_LIVE_API", "")
    if raw_api_flag.strip():
        return _parse_live_api_flag(raw_api_flag)

    flags = FeatureFlags.load()
    return bool(getattr(flags, "meta_live", False))


def _raise_live_not_enabled_for_create() -> None:
    raise NotImplementedError(
        "Live Meta campaign creation requires explicit live enablement. "
        "Set SYNAPSE_FLAG_META_LIVE_API=1 only when doing live execution, "
        "or use the full publish pipeline. Default/off mode stays mock/compat."
    )


def _raise_live_not_enabled_for_pause() -> None:
    raise NotImplementedError(
        "Live Meta campaign pause requires explicit live enablement. "
        "Set SYNAPSE_FLAG_META_LIVE_API=1 only when doing live execution. "
        "Default/off mode stays mock/compat."
    )


def call_create_campaign(payload: MetaCampaignPayload | Mapping[str, Any]) -> Dict[str, Any]:
    """
    Live Meta create adapter.

    Compat contract preserved:
    - default/off mode => NotImplementedError
    - explicit live gate ON => real HTTP transport
    """
    if not _is_live_transport_enabled():
        _raise_live_not_enabled_for_create()

    api_payload = _campaign_payload_to_api_dict(payload)
    token = _require_env("META_ACCESS_TOKEN")
    ad_account_id = _normalize_ad_account_id(_require_env("META_AD_ACCOUNT_ID"))

    requested_status = str(api_payload.get("status") or "PAUSED")
    response = _post_form(
        _campaign_endpoint(ad_account_id),
        {
            **api_payload,
            "access_token": token,
        },
    )

    campaign_id = str(response.get("id") or response.get("campaign_id") or "")
    return {
        "id": campaign_id,
        "campaign_id": campaign_id,
        "status": str(response.get("status") or requested_status),
        "api_response": response,
    }


def call_pause_campaign(request: MetaPauseRequest | str) -> Dict[str, Any]:
    """
    Live Meta pause adapter.

    Compat contract preserved:
    - default/off mode => NotImplementedError
    - explicit live gate ON => real HTTP transport
    """
    if not _is_live_transport_enabled():
        _raise_live_not_enabled_for_pause()

    api_request = _pause_request_to_api_dict(request)
    token = _require_env("META_ACCESS_TOKEN")

    campaign_id = str(api_request.get("campaign_id") or "").strip()
    if not campaign_id:
        raise RuntimeError("Meta pause requires campaign_id")

    requested_status = str(api_request.get("status") or "PAUSED")
    form_fields: Dict[str, Any] = {
        "access_token": token,
        "status": requested_status,
    }
    for key, value in api_request.items():
        if key == "campaign_id":
            continue
        form_fields[key] = value

    response = _post_form(_pause_endpoint(campaign_id), form_fields)
    returned_id = str(response.get("id") or campaign_id)
    return {
        "id": returned_id,
        "campaign_id": campaign_id,
        "status": str(response.get("status") or requested_status),
        "api_response": response,
    }
