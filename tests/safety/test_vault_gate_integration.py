from decimal import Decimal

from infra.vault import Vault
from synapse.safety.limits import RiskLimits
from synapse.safety.integrations.vault_gate import VaultGateConfig, request_spend_with_gate


def test_vault_gate_blocks_large_request():
    vault = Vault.from_total(Decimal("1000.00"))

    cfg = VaultGateConfig(
        limits=RiskLimits(
            daily_loss_limit=0.05,            # 5% de 1000 = 50
            spend_rate_anomaly_mult=3.0,
            max_single_campaign_share=0.25,
        )
    )

    # amount=80 => 80/1000=8% > 5% => debe bloquear
    res = request_spend_with_gate(
        vault=vault,
        amount=Decimal("80.00"),
        bucket="operational",
        cfg=cfg,
    )

    assert res.executed is False


def test_vault_gate_allows_small_request():
    vault = Vault.from_total(Decimal("1000.00"))

    cfg = VaultGateConfig(
        limits=RiskLimits(
            daily_loss_limit=0.05,
            spend_rate_anomaly_mult=3.0,
            max_single_campaign_share=0.25,
        )
    )

    # amount=10 => 1% <= 5% => permite
    res = request_spend_with_gate(
        vault=vault,
        amount=Decimal("10.00"),
        bucket="operational",
        cfg=cfg,
    )

    assert res.executed is True