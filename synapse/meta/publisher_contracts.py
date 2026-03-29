from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional


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
        payload.update(dict(self.extra))
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
        payload: Dict[str, Any] = {
            "campaign_id": self.campaign_id,
            "status": self.status,
        }
        payload.update(dict(self.extra))
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
