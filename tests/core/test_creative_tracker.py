# V3GAP:B-03_creative_fatigue_detector

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from synapse.core.creative_tracker import CreativeTracker


class TestCreativeTracker:
    def test_register(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        assert item.product_id == "P1"
        assert item.status == "untested"

    def test_update_metrics(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        updated = t.update_metrics(item.variant_id, Decimal("20"), 1000, 50, 2, Decimal("100"))
        assert updated.spend_total == Decimal("20")
        assert updated.roas == Decimal("5")

    def test_change_status(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        updated = t.change_status(item.variant_id, "active")
        assert updated.status == "active"

    def test_kill_with_reason(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        updated = t.change_status(item.variant_id, "killed", reason="bad_roas", decision_id="D1")
        assert updated.kill_reason == "bad_roas"
        assert updated.kill_decision_id == "D1"

    def test_get_active(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        a = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        b = t.register("P1", "benefit", "hook", "image_single", "assets/b.png")
        t.change_status(a.variant_id, "active")
        active = t.get_active("P1")
        assert len(active) == 1
        assert active[0].variant_id == a.variant_id

    def test_compare(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        a = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        b = t.register("P1", "benefit", "hook", "image_single", "assets/b.png")
        t.update_metrics(a.variant_id, Decimal("20"), 1000, 50, 2, Decimal("60"))
        t.update_metrics(b.variant_id, Decimal("20"), 1000, 50, 2, Decimal("120"))
        report = t.compare("P1")
        assert report.best_variant_id == b.variant_id
        assert report.worst_variant_id == a.variant_id

    def test_invalid_status_raises(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        with pytest.raises(ValueError):
            t.change_status(item.variant_id, "bad-status")

    def test_variant_is_frozen(self, tmp_path):
        t = CreativeTracker(str(tmp_path / "variants.jsonl"))
        item = t.register("P1", "benefit", "hook", "image_single", "assets/a.png")
        with pytest.raises(FrozenInstanceError):
            item.status = "x"