# tests/discovery/test_pipeline_orchestrator.py
import pytest
import tempfile
import csv
from pathlib import Path
from synapse.discovery import (
    PipelineOrchestrator, PipelineConfig, PipelineResult,
    run_pipeline, discover_products, NicheSelector
)


@pytest.fixture
def temp_setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create catalog
        catalog_path = Path(tmpdir) / "catalog.csv"
        with open(catalog_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "category", "price", "cost", "rating", "reviews"])
            writer.writeheader()
            writer.writerow({"id": "1", "title": "Audifonos Bluetooth Pro", "category": "audio", "price": "599", "cost": "180", "rating": "4.7", "reviews": "150"})
            writer.writerow({"id": "2", "title": "Bocina Speaker Portatil", "category": "audio", "price": "450", "cost": "135", "rating": "4.2", "reviews": "80"})
            writer.writerow({"id": "3", "title": "Audifonos TWS Earbuds", "category": "audio", "price": "399", "cost": "120", "rating": "4.5", "reviews": "200"})
        
        yield {
            "tmpdir": tmpdir,
            "catalog": str(catalog_path),
            "output": str(Path(tmpdir) / "output"),
        }


class TestPipelineOrchestrator:
    def test_run_returns_result(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        assert isinstance(result, PipelineResult)
    
    def test_run_scans_catalog(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        assert result.scan_result is not None
        assert result.scan_result.matched_products > 0
    
    def test_run_ranks_products(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        assert result.ranking_result is not None
        assert len(result.top_products) > 0
    
    def test_run_respects_top_n(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False, top_n=2)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        assert len(result.top_products) <= 2
    
    def test_run_completes_successfully(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        assert result.status == "completed"
    
    def test_run_saves_results(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False, save_results=True)
        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run(niche_id="audio_personal", csv_path=temp_setup["catalog"])
        summary_files = list(Path(temp_setup["output"]).glob("*_summary.json"))
        assert len(summary_files) >= 1
    
    def test_run_without_niche_fails(self, temp_setup):
        config = PipelineConfig(output_dir=temp_setup["output"], generate_kits=False)
        orchestrator = PipelineOrchestrator(config)
        orchestrator.niche_selector.clear_selection()
        result = orchestrator.run(csv_path=temp_setup["catalog"])
        assert result.status == "failed"


class TestRunPipeline:
    def test_run_pipeline_helper(self, temp_setup):
        result = run_pipeline("audio_personal", csv_path=temp_setup["catalog"], top_n=3)
        assert result.status == "completed"


class TestDiscoverProducts:
    def test_discover_products_helper(self, temp_setup):
        products = discover_products("audio_personal", csv_path=temp_setup["catalog"], top_n=2)
        assert len(products) <= 2
