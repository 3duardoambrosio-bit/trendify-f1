# tests/discovery/test_catalog_scanner.py
import pytest
import tempfile
import csv
from pathlib import Path
from synapse.discovery import CatalogScanner, ProductCandidate, ScanResult, scan_niche


@pytest.fixture
def temp_catalog():
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "test_catalog.csv"
        with open(catalog_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "category", "price", "cost", "rating", "reviews"])
            writer.writeheader()
            writer.writerow({"id": "1", "title": "Audifonos Bluetooth TWS Pro", "category": "electronics/audio", "price": "599", "cost": "180", "rating": "4.5", "reviews": "120"})
            writer.writerow({"id": "2", "title": "Bocina Portatil Speaker 10W", "category": "electronics/audio", "price": "450", "cost": "135", "rating": "4.2", "reviews": "80"})
            writer.writerow({"id": "3", "title": "Cable USB Repuesto", "category": "electronics/cables", "price": "50", "cost": "15", "rating": "4.0", "reviews": "200"})
            writer.writerow({"id": "4", "title": "Smartwatch Fitness Tracker", "category": "electronics/wearables", "price": "899", "cost": "270", "rating": "4.3", "reviews": "95"})
            writer.writerow({"id": "5", "title": "Organizador Closet Grande", "category": "home/organization", "price": "350", "cost": "105", "rating": "4.6", "reviews": "150"})
        yield str(catalog_path)


class TestCatalogScanner:
    def test_scan_returns_result(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog)
        assert isinstance(result, ScanResult)
    
    def test_scan_matches_keywords(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_margin=0, min_price=0)
        assert result.matched_products >= 2
    
    def test_scan_excludes_keywords(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_margin=0, min_price=0)
        titles = [c.title for c in result.candidates]
        assert not any("Repuesto" in t for t in titles)
    
    def test_scan_applies_margin_filter(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_margin=50)
        for c in result.candidates:
            assert c.margin_percent >= 50
    
    def test_scan_applies_price_filter(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_price=400, max_price=700)
        for c in result.candidates:
            assert 400 <= c.price <= 700
    
    def test_candidates_have_match_score(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_margin=0, min_price=0)
        for c in result.candidates:
            assert c.match_score > 0
    
    def test_candidates_sorted_by_score(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path=temp_catalog, min_margin=0, min_price=0)
        scores = [c.match_score for c in result.candidates]
        assert scores == sorted(scores, reverse=True)
    
    def test_scan_home_organization(self, temp_catalog):
        scanner = CatalogScanner()
        result = scanner.scan("home_organization", csv_path=temp_catalog, min_margin=0, min_price=0)
        assert result.matched_products >= 1


class TestProductCandidate:
    def test_margin_calculation(self):
        p = ProductCandidate(product_id="1", title="Test", category="test", price=100, cost=30)
        assert p.margin_absolute == 70
        assert p.margin_percent == 70.0


class TestQuickScan:
    def test_quick_scan(self, temp_catalog):
        scanner = CatalogScanner()
        candidates = scanner.quick_scan("audio_personal")
        assert isinstance(candidates, list)
