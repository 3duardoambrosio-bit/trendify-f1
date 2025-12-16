def test_cashflow_v1_exports_legacy_contract():
    from vault.cashflow_v1 import CashflowConfig, CashflowState, CashflowModel
    assert CashflowConfig is not None
    assert CashflowState is not None
    assert CashflowModel is not None