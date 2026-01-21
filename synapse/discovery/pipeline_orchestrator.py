# synapse/discovery/pipeline_orchestrator.py
"""
Pipeline Orchestrator - E2E: nicho -> scan -> rank -> top -> kits.

Un comando = De nicho seleccionado a marketing kits listos.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from .niche_selector import NicheSelector, NicheProfile
from .catalog_scanner import CatalogScanner, ProductCandidate, ScanResult
from .product_ranker import ProductRanker, ProductScore, RankingResult


@dataclass
class PipelineConfig:
    """Configuracion del pipeline."""
    # Scan config
    min_margin: float = 40.0
    min_price: float = 100.0
    max_price: float = 2000.0
    min_rating: float = 3.5
    scan_limit: int = 200
    
    # Rank config
    top_n: int = 10
    min_score: float = 0.4
    
    # Output config
    generate_kits: bool = True
    save_results: bool = True
    output_dir: str = "data/pipeline"


@dataclass
class PipelineResult:
    """Resultado completo del pipeline."""
    pipeline_id: str
    executed_at: str
    
    # Niche
    niche_id: str
    niche_name: str
    
    # Stages
    scan_result: Optional[ScanResult] = None
    ranking_result: Optional[RankingResult] = None
    
    # Final output
    top_products: List[ProductScore] = field(default_factory=list)
    
    # Kits generated (if enabled)
    kits_generated: int = 0
    kit_paths: List[str] = field(default_factory=list)
    
    # Status
    status: str = "pending"  # pending, scanning, ranking, generating, completed, failed
    error: str = ""
    
    # Timing
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "executed_at": self.executed_at,
            "niche_id": self.niche_id,
            "niche_name": self.niche_name,
            "status": self.status,
            "top_products_count": len(self.top_products),
            "kits_generated": self.kits_generated,
            "duration_seconds": self.duration_seconds,
        }


class PipelineOrchestrator:
    """
    Orquesta el pipeline completo de descubrimiento.
    
    Uso:
        orchestrator = PipelineOrchestrator()
        result = orchestrator.run(niche_id="audio_personal")
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.niche_selector = NicheSelector()
        self.catalog_scanner = CatalogScanner()
        self.product_ranker = ProductRanker()
        
        # Ensure output dir
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def run(
        self,
        niche_id: Optional[str] = None,
        csv_path: Optional[str] = None,
        config_override: Optional[Dict] = None,
    ) -> PipelineResult:
        """
        Ejecuta pipeline completo.
        
        Args:
            niche_id: ID del nicho (usa seleccion actual si no se especifica)
            csv_path: Path al CSV del catalogo
            config_override: Override de configuracion
            
        Returns:
            PipelineResult con todos los outputs
        """
        start_time = datetime.now(timezone.utc)
        pipeline_id = f"pipe_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        # Get niche
        if niche_id:
            niche = self.niche_selector.get(niche_id)
        else:
            niche = self.niche_selector.get_current_profile()
        
        if not niche:
            return PipelineResult(
                pipeline_id=pipeline_id,
                executed_at=start_time.isoformat(),
                niche_id="",
                niche_name="",
                status="failed",
                error="No niche selected or specified",
            )
        
        result = PipelineResult(
            pipeline_id=pipeline_id,
            executed_at=start_time.isoformat(),
            niche_id=niche.niche_id,
            niche_name=niche.name,
            status="scanning",
        )
        
        try:
            # Apply config override
            cfg = self.config
            if config_override:
                for k, v in config_override.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            
            # Stage 1: Scan catalog
            result.status = "scanning"
            scan_result = self.catalog_scanner.scan(
                niche_id=niche.niche_id,
                csv_path=csv_path,
                min_margin=cfg.min_margin,
                min_price=cfg.min_price,
                max_price=cfg.max_price,
                min_rating=cfg.min_rating,
                limit=cfg.scan_limit,
            )
            result.scan_result = scan_result
            
            if not scan_result.candidates:
                result.status = "completed"
                result.error = "No candidates found in scan"
                return result
            
            # Stage 2: Rank products
            result.status = "ranking"
            ranking_result = self.product_ranker.rank(
                candidates=scan_result.candidates,
                top_n=cfg.top_n,
                min_score=cfg.min_score,
            )
            ranking_result.niche_id = niche.niche_id
            result.ranking_result = ranking_result
            result.top_products = ranking_result.ranked_products
            
            if not ranking_result.ranked_products:
                result.status = "completed"
                result.error = "No products passed ranking threshold"
                return result
            
            # Stage 3: Generate kits (if enabled)
            if cfg.generate_kits:
                result.status = "generating"
                kit_paths = self._generate_kits(result.top_products, niche)
                result.kit_paths = kit_paths
                result.kits_generated = len(kit_paths)
            
            # Save results
            if cfg.save_results:
                self._save_result(result)
            
            result.status = "completed"
            
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
        
        finally:
            end_time = datetime.now(timezone.utc)
            result.duration_seconds = (end_time - start_time).total_seconds()
        
        return result
    
    def _generate_kits(self, products: List[ProductScore], niche: NicheProfile) -> List[str]:
        """Genera marketing kits para productos top."""
        kit_paths = []
        
        try:
            from synapse.marketing_os import run_wave
            from synapse.marketing_os.models import ProductContext
            
            for product in products[:5]:  # Max 5 kits
                try:
                    # Create ProductContext from ProductScore
                    context = ProductContext(
                        product_id=product.product_id,
                        name=product.title,
                        category=niche.category.value,
                        price=product.price,
                        cost=product.price * (1 - product.margin_percent / 100),
                    )
                    
                    # Run wave
                    wave_result = run_wave(
                        product_id=product.product_id,
                        name=product.title,
                        category=niche.category.value,
                        price=product.price,
                        cost=product.price * (1 - product.margin_percent / 100),
                        force=True,
                    )
                    
                    if wave_result.kit_path:
                        kit_paths.append(wave_result.kit_path)
                        
                except Exception:
                    continue
                    
        except ImportError:
            # Marketing OS not available
            pass
        
        return kit_paths
    
    def _save_result(self, result: PipelineResult):
        """Guarda resultado del pipeline."""
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save summary
        summary_path = output_dir / f"{result.pipeline_id}_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        # Save top products detail
        if result.top_products:
            products_path = output_dir / f"{result.pipeline_id}_products.json"
            products_data = [asdict(p) for p in result.top_products]
            with open(products_path, "w", encoding="utf-8") as f:
                json.dump(products_data, f, indent=2, ensure_ascii=False)
    
    def get_status(self, pipeline_id: str) -> Optional[Dict]:
        """Obtiene status de un pipeline ejecutado."""
        summary_path = Path(self.config.output_dir) / f"{pipeline_id}_summary.json"
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        return None


def run_pipeline(niche_id: str, csv_path: Optional[str] = None, top_n: int = 10) -> PipelineResult:
    """Helper para ejecutar pipeline."""
    config = PipelineConfig(top_n=top_n, generate_kits=False)
    orchestrator = PipelineOrchestrator(config)
    return orchestrator.run(niche_id=niche_id, csv_path=csv_path)


def discover_products(niche_id: str, csv_path: str, top_n: int = 5) -> List[ProductScore]:
    """Helper simple: retorna top productos."""
    result = run_pipeline(niche_id, csv_path, top_n)
    return result.top_products
