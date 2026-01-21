# synapse/marketing_os/wave_runner.py
"""
Wave Runner - Pipeline E2E para generacion de Marketing Kits.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ProductContext, InterrogationVerdict
from .interrogation_engine import InterrogationEngine
from .creative_factory import CreativeFactory


WAVE_VERSION = "05"
SCHEMA_VERSION = "1.0.0"

DEFAULT_PATHS = {
    "catalog": Path("data/catalog/candidates_real.csv"),
    "evidence": Path("data/evidence/products"),
    "output": Path("data/marketing/kits"),
    "ledger": Path("data/ledger"),
    "manifests": Path("data/marketing/manifests"),
}


@dataclass
class WaveResult:
    wave_id: str
    product_id: str
    status: str
    message: str
    kit_path: Optional[str] = None
    manifest_path: Optional[str] = None
    hooks_generated: int = 0
    scripts_generated: int = 0
    quality_score: float = 0.0
    input_hash: str = ""
    output_hash: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    interrogation_verdict: str = ""
    interrogation_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WaveRunner:
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        ledger_dir: Optional[Path] = None,
        manifest_dir: Optional[Path] = None,
    ):
        self.output_dir = output_dir or DEFAULT_PATHS["output"]
        self.ledger_dir = ledger_dir or DEFAULT_PATHS["ledger"]
        self.manifest_dir = manifest_dir or DEFAULT_PATHS["manifests"]
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        
        self.interrogation_engine = InterrogationEngine()
        self.creative_factory = CreativeFactory()
    
    def run(
        self,
        product: ProductContext,
        force: bool = False,
        config: Optional[Dict] = None,
    ) -> WaveResult:
        started_at = datetime.now(timezone.utc)
        wave_id = self._generate_wave_id(product.product_id)
        input_hash = product.input_hash()
        
        if not force:
            existing = self._check_existing(product.product_id, input_hash)
            if existing:
                return WaveResult(
                    wave_id=wave_id,
                    product_id=product.product_id,
                    status="SKIPPED",
                    message=f"Kit already exists with same input_hash: {input_hash}",
                    input_hash=input_hash,
                    started_at=started_at.isoformat(),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
        
        try:
            interrogation = self.interrogation_engine.interrogate(product)
            
            if interrogation.verdict == InterrogationVerdict.BLOCK:
                self._log_event("WAVE_BLOCKED", product.product_id, {
                    "wave_id": wave_id,
                    "reason": "Interrogation BLOCK",
                    "blocking_reasons": interrogation.blocking_reasons,
                    "score": interrogation.total_score,
                })
                
                return WaveResult(
                    wave_id=wave_id,
                    product_id=product.product_id,
                    status="BLOCKED",
                    message=f"Interrogation BLOCK: {interrogation.blocking_reasons}",
                    input_hash=input_hash,
                    interrogation_verdict=interrogation.verdict.value,
                    interrogation_score=interrogation.total_score,
                    started_at=started_at.isoformat(),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            
            kit = self.creative_factory.generate_kit(product, interrogation, config)
            kit_path = self._write_kit(product.product_id, wave_id, kit)
            manifest_path = self._write_manifest(product.product_id, wave_id, kit, input_hash)
            output_hash = self._compute_output_hash(kit)
            
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            self._log_event("WAVE_COMPLETED", product.product_id, {
                "wave_id": wave_id,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "hooks_count": len(kit["hooks"]),
                "quality_score": kit["manifest"].quality_score,
                "duration_seconds": duration,
            })
            
            return WaveResult(
                wave_id=wave_id,
                product_id=product.product_id,
                status="SUCCESS",
                message="Kit generated successfully",
                kit_path=str(kit_path),
                manifest_path=str(manifest_path),
                hooks_generated=len(kit["hooks"]),
                scripts_generated=len(kit["scripts_7s"]) + len(kit["scripts_15s"]) + len(kit["scripts_30s"]),
                quality_score=kit["manifest"].quality_score,
                input_hash=input_hash,
                output_hash=output_hash,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                duration_seconds=duration,
                interrogation_verdict=interrogation.verdict.value,
                interrogation_score=interrogation.total_score,
            )
            
        except Exception as e:
            self._log_event("WAVE_ERROR", product.product_id, {"wave_id": wave_id, "error": str(e)})
            return WaveResult(
                wave_id=wave_id,
                product_id=product.product_id,
                status="ERROR",
                message=f"Error: {str(e)}",
                input_hash=input_hash,
                started_at=started_at.isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
    
    def run_batch(self, products: List[ProductContext], force: bool = False, config: Optional[Dict] = None) -> List[WaveResult]:
        return [self.run(p, force=force, config=config) for p in products]
    
    def _generate_wave_id(self, product_id: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"wave{WAVE_VERSION}_{product_id}_{timestamp}"
    
    def _check_existing(self, product_id: str, input_hash: str) -> bool:
        for manifest_file in self.manifest_dir.glob(f"{product_id}_*.json"):
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    if manifest.get("input_hash") == input_hash:
                        return True
            except:
                continue
        return False
    
    def _write_kit(self, product_id: str, wave_id: str, kit: Dict) -> Path:
        kit_data = {
            "schema_version": SCHEMA_VERSION,
            "wave_id": wave_id,
            "product_id": product_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hooks": kit["hooks"],
            "scripts_7s": kit["scripts_7s"],
            "scripts_15s": kit["scripts_15s"],
            "scripts_30s": kit["scripts_30s"],
            "primary_texts": kit["primary_texts"],
            "headlines": kit["headlines"],
            "landing_skeleton": kit["landing_skeleton"],
            "objection_matrix": kit["objection_matrix"],
        }
        filepath = self.output_dir / f"{product_id}_{wave_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(kit_data, f, ensure_ascii=False, indent=2)
        return filepath
    
    def _write_manifest(self, product_id: str, wave_id: str, kit: Dict, input_hash: str) -> Path:
        manifest = kit["manifest"]
        manifest_data = {
            "schema_version": SCHEMA_VERSION,
            "wave_id": wave_id,
            "product_id": product_id,
            "product_name": manifest.product_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_hash": input_hash,
            "output_hash": self._compute_output_hash(kit),
            "counts": {
                "hooks": manifest.hooks_count,
                "scripts_7s": manifest.scripts_7s_count,
                "scripts_15s": manifest.scripts_15s_count,
                "scripts_30s": manifest.scripts_30s_count,
                "primary_texts": manifest.primary_texts_count,
                "headlines": manifest.headlines_count,
            },
            "quality_score": manifest.quality_score,
            "interrogation": {
                "verdict": manifest.interrogation_verdict,
                "score": manifest.interrogation_score,
            },
        }
        filepath = self.manifest_dir / f"{product_id}_manifest_{wave_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        return filepath
    
    def _compute_output_hash(self, kit: Dict) -> str:
        content = json.dumps({"hooks": [h["content"] for h in kit["hooks"]]}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _log_event(self, event_type: str, entity_id: str, payload: Dict):
        try:
            from synapse.infra.ledger import Ledger
            ledger = Ledger(str(self.ledger_dir))
            ledger.write(event_type=event_type, entity_type="product", entity_id=entity_id, payload=payload, wave_id=payload.get("wave_id", ""))
        except:
            pass


def run_wave(product_id: str, name: str, category: str, price: float, cost: float, description: str = "", unique_features: Optional[List[str]] = None, force: bool = False) -> WaveResult:
    product = ProductContext(product_id=product_id, name=name, category=category, price=price, cost=cost, description=description, unique_features=unique_features or [])
    runner = WaveRunner()
    return runner.run(product, force=force)


def run_wave_from_csv(product_id: str, csv_path: str = "data/catalog/candidates_real.csv", force: bool = False) -> WaveResult:
    import csv
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("candidate_id") == product_id:
                product = ProductContext(product_id=product_id, name=row.get("title", "Unknown"), category=row.get("category", "unknown"), price=float(row.get("price", 0)), cost=float(row.get("price", 0)) * 0.3)
                return WaveRunner().run(product, force=force)
    raise ValueError(f"Product {product_id} not found in CSV")
