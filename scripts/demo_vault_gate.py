from __future__ import annotations

from pathlib import Path
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.vault import Vault
from synapse.safety.integrations.vault_gate import request_spend_with_gate, VaultGateConfig
from synapse.safety.limits import RiskLimits


def main() -> None:
    # Vault infra tiene from_total
    vault = Vault.from_total(Decimal("1000.00"))

    cfg = VaultGateConfig(
        limits=RiskLimits(
            daily_loss_limit=0.05,
            spend_rate_anomaly_mult=3.0,
            max_single_campaign_share=0.25,
        )
    )

    ok = request_spend_with_gate(vault=vault, amount=Decimal("10.00"), bucket="operational", cfg=cfg)
    print("OK executed:", ok.executed, "result:", ok.result)

    nope = request_spend_with_gate(vault=vault, amount=Decimal("80.00"), bucket="operational", cfg=cfg)
    print("NOPE executed:", nope.executed, "error:", nope.error)


if __name__ == "__main__":
    main()
