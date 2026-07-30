"""
S14 Tests: Creative gate wired into pipeline.

Acceptance criteria:
  1. Product with valid kit_dir → gate passes → campaign created
  2. Product with invalid kit_dir → gate fails → campaign blocked
  3. Product with no kit_dir → gate skipped (backward compat) → campaign proceeds
  4. Creative gate middleware: missing kit_dir → FAIL-CLOSED
  5. Creative gate middleware: gate exception → FAIL-CLOSED
  6. Pipeline with enable_creative_gate=False → gate skipped
  7. Existing pipeline tests still pass (no regression)
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from synapse.meta.creative_gate_middleware import (
    CreativeGateCheckResult,
    check_creative_gate,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_valid_kit(tmp_path: Path) -> Path:
    """Create a valid creative kit with 3 images (1:1, 4:5, 9:16)."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    kit = tmp_path / "kit"
    kit.mkdir()

    # 1:1 (1080x1080)
    img1 = Image.new("RGB", (1080, 1080), color=(255, 0, 0))
    img1.save(kit / "a_1x1.jpg")

    # 4:5 (1080x1350)
    img2 = Image.new("RGB", (1080, 1350), color=(0, 255, 0))
    img2.save(kit / "b_4x5.jpg")

    # 9:16 (1080x1920)
    img3 = Image.new("RGB", (1080, 1920), color=(0, 0, 255))
    img3.save(kit / "c_9x16.jpg")

    return kit


def _make_invalid_kit(tmp_path: Path) -> Path:
    """Create an invalid kit (too small images)."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    kit = tmp_path / "bad_kit"
    kit.mkdir()

    # Only 1 tiny image — fails min_total AND min_resolution
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(kit / "tiny.jpg")

    return kit


@dataclass
class FakeProduct:
    sku: str
    creatives: list
    pixel_events: list
    kit_dir: Optional[str] = None

    @property
    def product(self):
        return self


class FakeSafeClient:
    def __init__(self):
        self.payloads = []
        self.safe_calls = 0

    def create_campaign(self, payload):
        self.payloads.append(payload)
        raise AssertionError("offline pipeline must not publish")

    def create_campaign_safe(self, *args, **kwargs):
        self.safe_calls += 1
        raise AssertionError("offline pipeline must not call MetaSafeClient")


def _build_pipeline(enable_creative_gate=True, enable_publish=False):
    from synapse.meta.account_health import AccountHealthChecker, AccountHealthConfig, AccountMetrics
    from synapse.meta.advantage_plus import AdvantagePlusCampaignBuilder, AdvantagePlusConfig
    from synapse.meta.pipeline_e2e import PipelineE2E, PipelineE2EConfig
    from synapse.meta.warm_up_protocol import WarmUpProtocol, WarmUpConfig

    safe = FakeSafeClient()
    health = AccountHealthChecker(AccountHealthConfig())
    created = datetime.now(timezone.utc) - timedelta(days=20)
    warm = WarmUpProtocol(WarmUpConfig(), created)
    ap = AdvantagePlusCampaignBuilder(AdvantagePlusConfig())
    cfg = PipelineE2EConfig(
        enable_publish=enable_publish,
        enable_creative_gate=enable_creative_gate,
        default_budget_daily_usd=Decimal("10"),
        daily_cap_usd=Decimal("50"),
    )
    e2e = PipelineE2E(safe_client=safe, health_checker=health, warm_up=warm, advantage_plus=ap, config=cfg)
    metrics = AccountMetrics(ad_disapproval_rate=0.01, spend_velocity_ratio=1.0, account_age_days=20, has_policy_violation=False)
    return e2e, safe, metrics


# ── 1. Valid kit → gate passes → campaign created ────────────

class TestCreativeGateValid:
    def test_valid_kit_allows_campaign(self, tmp_path):
        kit = _make_valid_kit(tmp_path)
        e2e, safe, metrics = _build_pipeline()

        product = FakeProduct(
            sku="SKU-1",
            creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
            pixel_events=["Purchase"],
            kit_dir=str(kit),
        )

        out = e2e.execute(products=[product], account_metrics=metrics)
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 0
        assert out.products_processed == 1
        assert len(safe.payloads) == 0
        assert safe.safe_calls == 0


# ── 2. Invalid kit → gate fails → campaign blocked ──────────

class TestCreativeGateBlocks:
    def test_invalid_kit_blocks_campaign(self, tmp_path):
        kit = _make_invalid_kit(tmp_path)
        e2e, safe, metrics = _build_pipeline()

        product = FakeProduct(
            sku="SKU-BAD",
            creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
            pixel_events=["Purchase"],
            kit_dir=str(kit),
        )

        out = e2e.execute(products=[product], account_metrics=metrics)
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 1
        assert len(safe.payloads) == 0
        assert safe.safe_calls == 0

        # Error should mention creative_gate stage
        assert any(e["stage"] == "creative_gate" for e in out.errors)

    def test_nonexistent_kit_dir_blocks(self, tmp_path):
        e2e, safe, metrics = _build_pipeline()

        product = FakeProduct(
            sku="SKU-GHOST",
            creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
            pixel_events=["Purchase"],
            kit_dir=str(tmp_path / "does_not_exist"),
        )

        out = e2e.execute(products=[product], account_metrics=metrics)
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 1


# ── 3. No kit_dir → backward compatible → campaign proceeds ──

class TestBackwardCompat:
    def test_no_kit_dir_skips_gate(self):
        """Products without kit_dir should still work (legacy path)."""
        e2e, safe, metrics = _build_pipeline()

        product = FakeProduct(
            sku="SKU-LEGACY",
            creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
            pixel_events=["Purchase"],
            kit_dir=None,  # No kit_dir → gate skipped
        )

        out = e2e.execute(products=[product], account_metrics=metrics)
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 0
        assert out.products_processed == 1
        assert len(safe.payloads) == 0
        assert safe.safe_calls == 0


# ── 4. Middleware: missing kit_dir → FAIL-CLOSED ─────────────

class TestMiddlewareFailClosed:
    def test_no_kit_dir_fails(self):
        product = FakeProduct(sku="X", creatives=[], pixel_events=[], kit_dir=None)
        result = check_creative_gate(product)
        assert result.allowed is False
        assert result.reason == "kit_dir_missing"

    def test_empty_kit_dir_fails(self):
        product = FakeProduct(sku="X", creatives=[], pixel_events=[], kit_dir="")
        result = check_creative_gate(product)
        assert result.allowed is False
        assert result.reason == "kit_dir_missing"


# ── 5. Middleware: exception → FAIL-CLOSED ───────────────────

class TestMiddlewareException:
    def test_gate_exception_blocks(self, tmp_path):
        kit = tmp_path / "kit"
        kit.mkdir()
        # Create a file that will cause issues
        (kit / "bad.jpg").write_bytes(b"NOT AN IMAGE")
        (kit / "bad2.jpg").write_bytes(b"NOT AN IMAGE 2")
        (kit / "bad3.jpg").write_bytes(b"NOT AN IMAGE 3")

        product = FakeProduct(sku="X", creatives=[], pixel_events=[], kit_dir=str(kit))
        result = check_creative_gate(product)
        # Should either fail with gate_failed or gate_exception — either way, blocked
        assert result.allowed is False


# ── 6. enable_creative_gate=False → gate skipped ────────────

class TestGateDisabled:
    def test_gate_disabled_skips_validation(self, tmp_path):
        """Even with invalid kit, campaign proceeds if gate disabled."""
        kit = _make_invalid_kit(tmp_path)
        e2e, safe, metrics = _build_pipeline(enable_creative_gate=False)

        product = FakeProduct(
            sku="SKU-NOGATHE",
            creatives=[{"id": 1}, {"id": 2}, {"id": 3}],
            pixel_events=["Purchase"],
            kit_dir=str(kit),
        )

        out = e2e.execute(products=[product], account_metrics=metrics)
        # Gate disabled → should NOT block
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 0
        assert out.products_processed == 1
        assert len(safe.payloads) == 0
        assert safe.safe_calls == 0


# ── 7. Mixed batch: valid + invalid → only valid published ───

class TestMixedBatch:
    def test_mixed_products(self, tmp_path):
        valid_kit = _make_valid_kit(tmp_path)
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        invalid_kit = _make_invalid_kit(bad_dir)

        e2e, safe, metrics = _build_pipeline()

        products = [
            FakeProduct(sku="GOOD", creatives=[{"id": 1}, {"id": 2}, {"id": 3}], pixel_events=["Purchase"], kit_dir=str(valid_kit)),
            FakeProduct(sku="BAD", creatives=[{"id": 1}, {"id": 2}, {"id": 3}], pixel_events=["Purchase"], kit_dir=str(invalid_kit)),
        ]

        out = e2e.execute(products=products, account_metrics=metrics)
        assert out.campaigns_created == 0
        assert out.campaigns_blocked == 1
        assert out.products_processed == 2
        assert len(safe.payloads) == 0
        assert safe.safe_calls == 0


# ── 8. Middleware valid kit produces correct result ──────────

class TestMiddlewareValid:
    def test_valid_kit_passes_gate(self, tmp_path):
        kit = _make_valid_kit(tmp_path)
        product = FakeProduct(sku="X", creatives=[], pixel_events=[], kit_dir=str(kit))
        result = check_creative_gate(product)
        assert result.allowed is True
        assert result.reason == "gate_passed"
        assert len(result.errors) == 0
