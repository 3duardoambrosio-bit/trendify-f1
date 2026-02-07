import pytest
import warnings
warnings.filterwarnings(
    "ignore",
    message=r"^capital_shield v1 is deprecated, use capital_shield_v2$",
    category=DeprecationWarning,
)
from ops.capital_shield_v1_DEPRECATED import CapitalShield
def test_allows_spend_under_daily_cap():
    shield = CapitalShield()

    d1 = shield.register_spend("prod_1", 10.0)
    d2 = shield.register_spend("prod_2", 15.0)

    assert d1.allowed is True
    assert d2.allowed is True
    assert d2.reason == "ok"


def test_blocks_when_daily_cap_exceeded():
    shield = CapitalShield()

    shield.register_spend("prod_1", 20.0)
    shield.register_spend("prod_2", 9.0)
    d3 = shield.register_spend("prod_3", 5.0)  # 20 + 9 + 5 = 34 > 30

    assert d3.allowed is False
    assert d3.reason == "hard_daily_cap_exceeded"


def test_warns_when_product_soft_cap_exceeded():
    shield = CapitalShield()

    # 10 / 30 = 0.33  â†’ ok
    shield.register_spend("prod_1", 10.0)

    # 15 / 30 = 0.50  â†’ > soft (0.40) pero < hard (0.70)
    d2 = shield.register_spend("prod_1", 5.0)

    assert d2.allowed is True
    assert "product_soft_cap_ratio_exceeded" in d2.soft_warnings


def test_blocks_when_product_hard_cap_exceeded():
    shield = CapitalShield()

    # 20 / 30 â‰ˆ 0.66 â†’ debajo del hard cap
    shield.register_spend("prod_1", 20.0)

    # 25 / 30 â‰ˆ 0.83 â†’ arriba del hard cap
    d2 = shield.register_spend("prod_1", 5.0)

    assert d2.allowed is False
    assert d2.reason == "product_hard_cap_ratio_exceeded"


