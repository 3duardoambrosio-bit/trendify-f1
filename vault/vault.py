from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Optional, Union, Dict, Any

from core.result import Ok, Err, Result

logger = logging.getLogger(__name__)

BudgetType = Literal["learning", "operational", "reserve"]
StateFile = Union[str, Path]

_SCHEMA = "vault_state_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dec(x: object) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        raise ValueError("bool is not a valid decimal input")
    try:
        return Decimal(str(x))
    except Exception as exc:
        raise ValueError(f"invalid decimal: {x!r}") from exc


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))


def _read_json(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError("empty state file")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("state must be a JSON object")
    return obj


@dataclass(frozen=True)
class SpendApproval:
    """
    Aprobación de gasto desde el Vault.
    """
    amount: Decimal
    budget_type: BudgetType


@dataclass(frozen=True)
class SpendError:
    """
    Error al intentar gastar desde el Vault.
    """
    message: str
    budget_type: Optional[BudgetType] = None


@dataclass
class Vault:
    """
    Vault con 3 buckets de capital:

    - learning_budget: para probar productos nuevos.
    - operational_budget: para operar/escalar.
    - reserve_budget: intocable.

    Invariantes:
    - Todos los budgets son >= 0.
    - learning_budget + operational_budget + reserve_budget = total_budget.
    - reserve_budget nunca se puede gastar vía request_spend.
    - spent nunca excede su budget.

    PERSISTENCE (P0-001):
    - state_file opcional: si se pasa y existe, se carga estado.
    - si el state está corrupto o no cuadra con el config => FAIL-CLOSED (raise).
    - si se aprueba gasto, se persiste atómicamente (tmp + fsync + replace).
    """

    total_budget: Decimal
    learning_budget: Decimal
    operational_budget: Decimal
    reserve_budget: Decimal

    learning_spent: Decimal = Decimal("0")
    operational_spent: Decimal = Decimal("0")

    state_file: Optional[StateFile] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # 1) Coerción a Decimal
        try:
            self.total_budget = _dec(self.total_budget)
            self.learning_budget = _dec(self.learning_budget)
            self.operational_budget = _dec(self.operational_budget)
            self.reserve_budget = _dec(self.reserve_budget)
            self.learning_spent = _dec(self.learning_spent)
            self.operational_spent = _dec(self.operational_spent)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid decimal value in Vault config: {exc}") from exc

        # 2) Normalizar state_file
        if self.state_file is not None and not isinstance(self.state_file, Path):
            self.state_file = Path(str(self.state_file))


        # 2b) state_file por ENV (OPT-IN)
        if self.state_file is None:
            env_path = os.getenv("SYNAPSE_VAULT_STATE_FILE")
            if env_path:
                self.state_file = Path(env_path)
        # 3) Validación base de budgets
        for name, value in [
            ("total_budget", self.total_budget),
            ("learning_budget", self.learning_budget),
            ("operational_budget", self.operational_budget),
            ("reserve_budget", self.reserve_budget),
        ]:
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

        if self.learning_budget + self.operational_budget + self.reserve_budget != self.total_budget:
            raise ValueError(
                "Vault budgets must sum exactly to total_budget "
                f"(learning + operational + reserve = {self.learning_budget + self.operational_budget + self.reserve_budget}, "
                f"total_budget = {self.total_budget})"
            )

        if self.learning_spent < 0 or self.operational_spent < 0:
            raise ValueError("Spent amounts must be non-negative")

        # 4) Load state si aplica (antes de checar límites de spent)
        if self.state_file is not None:
            sf: Path = self.state_file  # type: ignore[assignment]
            if sf.exists():
                self._load_state(sf)

        # 5) Validación final de spent vs budgets
        if self.learning_spent > self.learning_budget:
            raise ValueError("learning_spent cannot exceed learning_budget")

        if self.operational_spent > self.operational_budget:
            raise ValueError("operational_spent cannot exceed operational_budget")

    # --- Properties de conveniencia ---

    @property
    def total_spent(self) -> Decimal:
        return self.learning_spent + self.operational_spent

    @property
    def learning_remaining(self) -> Decimal:
        return self.learning_budget - self.learning_spent

    @property
    def operational_remaining(self) -> Decimal:
        return self.operational_budget - self.operational_spent

    @property
    def reserve_intact(self) -> bool:
        """
        Invariante fundamental:
        - reserve_budget nunca se toca vía request_spend.
        """
        return True

    # --- Persistence ---

    def _state_payload(self) -> Dict[str, Any]:
        return {
            "schema": _SCHEMA,
            "ts_utc": _utc_now_iso(),
            "budgets": {
                "total_budget": str(self.total_budget),
                "learning_budget": str(self.learning_budget),
                "operational_budget": str(self.operational_budget),
                "reserve_budget": str(self.reserve_budget),
            },
            "spent": {
                "learning_spent": str(self.learning_spent),
                "operational_spent": str(self.operational_spent),
            },
        }

    def _load_state(self, path: Path) -> None:
        try:
            obj = _read_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("VAULT_STATE_CORRUPTED: %s: %s — starting with defaults", path, exc)
            return

        if obj.get("schema") != _SCHEMA:
            logger.warning(
                "VAULT_STATE_UNSUPPORTED_SCHEMA: got=%r expected=%s — starting with defaults",
                obj.get("schema"), _SCHEMA,
            )
            return

        try:
            b = obj["budgets"]
            s = obj["spent"]
            lt = _dec(b["total_budget"])
            ll = _dec(b["learning_budget"])
            lo = _dec(b["operational_budget"])
            lr = _dec(b["reserve_budget"])
            lspent = _dec(s.get("learning_spent", "0"))
            ospent = _dec(s.get("operational_spent", "0"))
        except Exception as exc:
            logger.warning("VAULT_STATE_INVALID_SHAPE: %s: %s — starting with defaults", path, exc)
            return

        # Config mismatch => warn and start fresh
        if lt != self.total_budget or ll != self.learning_budget or lo != self.operational_budget or lr != self.reserve_budget:
            logger.warning(
                "VAULT_STATE_CONFIG_MISMATCH: state budgets do not match current config "
                "(state total=%s, learning=%s, operational=%s, reserve=%s) "
                "(cfg total=%s, learning=%s, operational=%s, reserve=%s) — starting with defaults",
                lt, ll, lo, lr,
                self.total_budget, self.learning_budget, self.operational_budget, self.reserve_budget,
            )
            return

        if lspent < 0 or ospent < 0:
            logger.warning("VAULT_STATE_INVALID_SPENT_NEGATIVE — starting with defaults")
            return

        # Aplicar spent
        self.learning_spent = lspent
        self.operational_spent = ospent

        logger.info("vault state loaded: %s", path)

    def persist(self) -> None:
        if self.state_file is None:
            return
        sf: Path = self.state_file  # type: ignore[assignment]
        payload = self._state_payload()
        _atomic_write_json(sf, payload)

    # --- Core API ---

    def request_spend(
        self,
        amount: Decimal,
        budget_type: BudgetType,
    ) -> Result[SpendApproval, SpendError]:
        """
        Solicita gastar `amount` desde uno de los budgets.

        Reglas:
        - amount debe ser > 0.
        - budget_type = "learning" | "operational" | "reserve".
        - "reserve" SIEMPRE devuelve Err: no se puede gastar.
        - Nunca se permite que learning_spent u operational_spent excedan sus budgets.
        - Si se aprueba, se persiste atómicamente si state_file está configurado.
        """
        try:
            dec_amount = _dec(amount)
        except ValueError:
            return Err(SpendError("Invalid amount", budget_type=budget_type))

        if dec_amount <= 0:
            return Err(SpendError("Amount must be positive", budget_type=budget_type))

        if budget_type == "reserve":
            return Err(
                SpendError(
                    message="Reserve budget is untouchable",
                    budget_type="reserve",
                )
            )

        if budget_type == "learning":
            if self.learning_spent + dec_amount > self.learning_budget:
                return Err(
                    SpendError(
                        message="Learning budget exceeded",
                        budget_type="learning",
                    )
                )
            self.learning_spent += dec_amount  # type: ignore[assignment]
            try:
                self.persist()
            except Exception as exc:
                # FAIL-CLOSED: si no se puede persistir, no seguimos operando en modo “dinero real”
                raise RuntimeError(f"VAULT_PERSIST_FAILED: {exc}") from exc
            return Ok(
                SpendApproval(
                    amount=dec_amount,
                    budget_type="learning",
                )
            )

        if budget_type == "operational":
            if self.operational_spent + dec_amount > self.operational_budget:
                return Err(
                    SpendError(
                        message="Operational budget exceeded",
                        budget_type="operational",
                    )
                )
            self.operational_spent += dec_amount  # type: ignore[assignment]
            try:
                self.persist()
            except Exception as exc:
                raise RuntimeError(f"VAULT_PERSIST_FAILED: {exc}") from exc
            return Ok(
                SpendApproval(
                    amount=dec_amount,
                    budget_type="operational",
                )
            )

        # Guardrail defensivo.
        return Err(
            SpendError(
                message=f"Unknown budget_type: {budget_type}",
                budget_type=budget_type,
            )
        )