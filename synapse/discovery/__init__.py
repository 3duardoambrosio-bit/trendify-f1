# synapse/discovery/__init__.py
from .niche_selector import (
    NicheSelector, NicheProfile, NicheSelection, NicheCategory, NicheRisk,
    CompetitionLevel, NICHE_CATALOG, list_niches, get_niche_keywords, get_niche_filters,
)
from .catalog_scanner import (
    CatalogScanner, ProductCandidate, ScanResult, scan_niche,
)
from .product_ranker import (
    ProductRanker, ProductScore, RankingResult, rank_products,
)
from .pipeline_orchestrator import (
    PipelineOrchestrator, PipelineConfig, PipelineResult,
    run_pipeline, discover_products,
)
__all__ = [
    "NicheSelector", "NicheProfile", "NicheSelection", "NicheCategory", "NicheRisk",
    "CompetitionLevel", "NICHE_CATALOG", "list_niches", "get_niche_keywords", "get_niche_filters",
    "CatalogScanner", "ProductCandidate", "ScanResult", "scan_niche",
    "ProductRanker", "ProductScore", "RankingResult", "rank_products",
    "PipelineOrchestrator", "PipelineConfig", "PipelineResult", "run_pipeline", "discover_products",
]
