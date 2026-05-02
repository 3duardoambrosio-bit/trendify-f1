from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

_logger = logging.getLogger(__name__)


FORBIDDEN_META_API_KEYS = frozenset(
    {
        "interests",
        "exclusions",
        "detailed_targeting",
        "interest_targeting",
        "instagram_actor_id",
    }
)


def _collect_forbidden_meta_api_key_paths(
    value: Any,
    *,
    path: str = "$",
    _seen: set[int] | None = None,
) -> list[str]:
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, (str, bytes, bytearray, int, float, bool)):
        return []

    value_id = id(value)
    if value_id in _seen:
        return []
    _seen.add(value_id)

    found: list[str] = []

    if isinstance(value, Mapping):
        items = value.items()
        path_builder = lambda key: f"{path}.{key}"
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = enumerate(value)
        path_builder = lambda key: f"{path}[{key}]"
    elif is_dataclass(value) and not isinstance(value, type):
        try:
            items = asdict(value).items()
        except (TypeError, ValueError):
            items = ()
        path_builder = lambda key: f"{path}.{key}"
    elif hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            dumped = value.model_dump()
        except (TypeError, ValueError, RuntimeError):
            dumped = {}
        items = dumped.items() if isinstance(dumped, Mapping) else ()
        path_builder = lambda key: f"{path}.{key}"
    elif hasattr(value, "dict") and callable(getattr(value, "dict")):
        try:
            dumped = value.dict()
        except (TypeError, ValueError, RuntimeError):
            dumped = {}
        items = dumped.items() if isinstance(dumped, Mapping) else ()
        path_builder = lambda key: f"{path}.{key}"
    elif hasattr(value, "__dict__"):
        items = vars(value).items()
        path_builder = lambda key: f"{path}.{key}"
    else:
        return []

    for raw_key, child in items:
        key = str(raw_key)
        child_path = path_builder(key)

        if key in FORBIDDEN_META_API_KEYS:
            found.append(child_path)

        found.extend(
            _collect_forbidden_meta_api_key_paths(
                child,
                path=child_path,
                _seen=_seen,
            )
        )

    return found
def reject_forbidden_meta_api_keys(payload: Mapping[str, Any], *, context: str) -> None:
    forbidden = sorted(set(_collect_forbidden_meta_api_key_paths(payload)))
    if forbidden:
        joined = ", ".join(forbidden)
        raise ValueError(f"{context} contains forbidden Meta API keys: {joined}")




def _warn_on_deprecated_meta_response_keys(api_response: Optional[Mapping[str, Any]], *, context: str) -> None:
    forbidden = sorted(set(_collect_forbidden_meta_api_key_paths(api_response)))
    if not forbidden:
        return
    _logger.warning(
        "deprecated_meta_response_keys_detected context=%s paths=%s",
        context,
        ", ".join(forbidden),
    )


def _copy_mapping(value: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    return dict(value)


@dataclass(frozen=True, slots=True)
class MetaCampaignPayload:
    name: str
    objective: str = "OUTCOME_SALES"
    status: str = "PAUSED"
    budget_mxn: Optional[Decimal] = None
    daily_budget_minor_units: Optional[int] = None
    targeting: Optional[Mapping[str, Any]] = None
    promoted_object: Optional[Mapping[str, Any]] = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> Dict[str, Any]:
        extra = dict(self.extra)
        reject_forbidden_meta_api_keys(extra, context="MetaCampaignPayload.extra")

        payload: Dict[str, Any] = {
            "name": self.name,
            "objective": self.objective,
            "status": self.status,
        }
        if self.budget_mxn is not None:
            payload["budget_mxn"] = str(self.budget_mxn)
        if self.daily_budget_minor_units is not None:
            payload["daily_budget_minor_units"] = int(self.daily_budget_minor_units)
        if self.targeting is not None:
            payload["targeting"] = _copy_mapping(self.targeting)
        if self.promoted_object is not None:
            payload["promoted_object"] = _copy_mapping(self.promoted_object)
        payload.update(extra)
        reject_forbidden_meta_api_keys(payload, context="MetaCampaignPayload")
        return payload


@dataclass(frozen=True, slots=True)
class MetaCampaignResponse:
    ok: bool
    campaign_id: Optional[str]
    status: str
    mode: str
    api_response: Optional[Mapping[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        _warn_on_deprecated_meta_response_keys(
            self.api_response,
            context=type(self).__name__,
        )

    @classmethod
    def from_mock(cls, campaign_id: str, status: str = "PAUSED") -> "MetaCampaignResponse":
        return cls(
            ok=True,
            campaign_id=campaign_id,
            status=status,
            mode="mock",
            api_response=None,
            error_code=None,
            error_message=None,
        )

    @classmethod
    def from_error(
        cls,
        error_code: str,
        error_message: str,
        *,
        campaign_id: Optional[str] = None,
        status: str = "PAUSED",
        mode: str = "error",
        api_response: Optional[Mapping[str, Any]] = None,
    ) -> "MetaCampaignResponse":
        return cls(
            ok=False,
            campaign_id=campaign_id,
            status=status,
            mode=mode,
            api_response=_copy_mapping(api_response),
            error_code=error_code,
            error_message=error_message,
        )


@dataclass(frozen=True, slots=True)
class MetaPauseRequest:
    campaign_id: str
    status: str = "PAUSED"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> Dict[str, Any]:
        extra = dict(self.extra)
        reject_forbidden_meta_api_keys(extra, context="MetaPauseRequest.extra")

        payload: Dict[str, Any] = {
            "campaign_id": self.campaign_id,
            "status": self.status,
        }
        payload.update(extra)
        reject_forbidden_meta_api_keys(payload, context="MetaPauseRequest")
        return payload


@dataclass(frozen=True, slots=True)
class MetaPauseResponse:
    ok: bool
    campaign_id: str
    status: str
    mode: str
    api_response: Optional[Mapping[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        _warn_on_deprecated_meta_response_keys(
            self.api_response,
            context=type(self).__name__,
        )

    @classmethod
    def from_mock(cls, campaign_id: str, status: str = "PAUSED") -> "MetaPauseResponse":
        return cls(
            ok=True,
            campaign_id=campaign_id,
            status=status,
            mode="mock",
            api_response=None,
            error_code=None,
            error_message=None,
        )

    @classmethod
    def from_error(
        cls,
        campaign_id: str,
        error_code: str,
        error_message: str,
        *,
        status: str = "PAUSED",
        mode: str = "error",
        api_response: Optional[Mapping[str, Any]] = None,
    ) -> "MetaPauseResponse":
        return cls(
            ok=False,
            campaign_id=campaign_id,
            status=status,
            mode=mode,
            api_response=_copy_mapping(api_response),
            error_code=error_code,
            error_message=error_message,
        )


__all__ = [
    "MetaCampaignPayload",
    "MetaCampaignResponse",
    "MetaPauseRequest",
    "MetaPauseResponse",
]
