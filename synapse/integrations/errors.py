from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


INTEGRATION_NOT_CONFIGURED = IntegrationError(
    code="INTEGRATION_NOT_CONFIGURED",
    message="Integration disabled or missing credentials/config.",
)