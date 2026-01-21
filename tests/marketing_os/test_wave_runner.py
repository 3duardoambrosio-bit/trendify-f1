# tests/marketing_os/test_wave_runner.py
import pytest
import tempfile
import json
from pathlib import Path
from synapse.marketing_os.models import ProductContext
from synapse.marketing_os.wave_runner import WaveRunner, run_wave, WaveResult


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        yield {"output": tmpdir / "kits", "ledger": tmpdir / "ledger", "manifest": tmpdir / "manifests"}


@pytest.fixture
def product():
    return ProductContext(product_id="34357", name="Audifonos Bluetooth M10", category="electronics/audio", price=599.0, cost=180.0, description="Audifonos inalambricos", unique_features=["20h bateria", "Bluetooth 5.0"])


@pytest.fixture
def runner(temp_dirs):
    return WaveRunner(output_dir=temp_dirs["output"], ledger_dir=temp_dirs["ledger"], manifest_dir=temp_dirs["manifest"])


class TestWaveRunner:
    def test_run_returns_wave_result(self, runner, product):
        result = runner.run(product)
        assert isinstance(result, WaveResult)
        assert result.wave_id
        assert result.product_id == "34357"
    
    def test_run_success_generates_kit(self, runner, product):
        result = runner.run(product)
        assert result.status == "SUCCESS"
        assert result.kit_path
        assert Path(result.kit_path).exists()
    
    def test_run_success_generates_manifest(self, runner, product):
        result = runner.run(product)
        assert result.status == "SUCCESS"
        assert result.manifest_path
        assert Path(result.manifest_path).exists()
    
    def test_kit_contains_all_components(self, runner, product):
        result = runner.run(product)
        with open(result.kit_path, "r", encoding="utf-8") as f:
            kit = json.load(f)
        assert "hooks" in kit
        assert "scripts_15s" in kit
        assert "headlines" in kit
        assert "schema_version" in kit
    
    def test_kit_has_content(self, runner, product):
        result = runner.run(product)
        with open(result.kit_path, "r", encoding="utf-8") as f:
            kit = json.load(f)
        assert len(kit["hooks"]) > 0
        assert len(kit["scripts_15s"]) > 0
    
    def test_manifest_has_hashes(self, runner, product):
        result = runner.run(product)
        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert "input_hash" in manifest
        assert "output_hash" in manifest
    
    def test_idempotency_skips_duplicate(self, runner, product):
        result1 = runner.run(product)
        result2 = runner.run(product)
        assert result1.status == "SUCCESS"
        assert result2.status == "SKIPPED"
    
    def test_force_regenerates(self, runner, product):
        result1 = runner.run(product)
        result2 = runner.run(product, force=True)
        assert result1.status == "SUCCESS"
        assert result2.status == "SUCCESS"
        # Both should generate kits (force bypasses idempotency)
        assert Path(result1.kit_path).exists()
        assert Path(result2.kit_path).exists()
    
    def test_result_has_metrics(self, runner, product):
        result = runner.run(product)
        assert result.hooks_generated > 0
        assert result.scripts_generated > 0
        assert result.quality_score > 0
    
    def test_result_has_interrogation_info(self, runner, product):
        result = runner.run(product)
        assert result.interrogation_verdict in ["launch", "needs_work", "block"]
        assert result.interrogation_score > 0
    
    def test_blocked_product_returns_blocked(self, runner):
        bad_product = ProductContext(product_id="bad123", name="Pastillas adelgazar milagro cura cancer", category="health", price=100, cost=10, description="Cura todo milagro garantizado")
        result = runner.run(bad_product)
        assert result.status == "BLOCKED"


class TestBatchProcessing:
    def test_run_batch_multiple_products(self, runner):
        products = [ProductContext(product_id=f"prod{i}", name=f"Product {i}", category="test", price=100*i, cost=30*i) for i in range(1, 4)]
        results = runner.run_batch(products, force=True)
        assert len(results) == 3
        assert all(r.status == "SUCCESS" for r in results)
