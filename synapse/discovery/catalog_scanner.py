# synapse/discovery/catalog_scanner.py
"""
Catalog Scanner - Filtra catalogo Droppi por nicho seleccionado.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json

from .niche_selector import NicheProfile, get_niche_filters, NICHE_CATALOG


@dataclass
class ProductCandidate:
    """Producto candidato del catalogo."""
    product_id: str
    title: str
    category: str
    price: float
    cost: float
    
    # Metricas de calidad
    rating: float = 0.0
    reviews: int = 0
    sales: int = 0
    
    # Supplier
    supplier_id: str = ""
    supplier_name: str = ""
    shipping_days: int = 7
    
    # Imagenes
    image_url: str = ""
    images_count: int = 0
    
    # Calculados
    margin_percent: float = 0.0
    margin_absolute: float = 0.0
    
    # Matching
    keyword_matches: List[str] = field(default_factory=list)
    match_score: float = 0.0
    
    def __post_init__(self):
        if self.price > 0 and self.cost > 0:
            self.margin_absolute = self.price - self.cost
            self.margin_percent = (self.margin_absolute / self.price) * 100


@dataclass
class ScanResult:
    """Resultado de escaneo de catalogo."""
    niche_id: str
    scanned_at: str
    total_products: int
    matched_products: int
    filtered_products: int
    
    # Filters applied
    filters: Dict[str, Any] = field(default_factory=dict)
    
    # Results
    candidates: List[ProductCandidate] = field(default_factory=list)
    
    # Stats
    avg_price: float = 0.0
    avg_margin: float = 0.0
    price_range: Tuple[float, float] = (0, 0)


class CatalogScanner:
    """
    Escanea catalogo y filtra por nicho.
    
    Uso:
        scanner = CatalogScanner()
        result = scanner.scan("audio_personal", csv_path="data/catalog/droppi.csv")
    """
    
    def __init__(self, catalog_dir: str = "data/catalog"):
        self.catalog_dir = Path(catalog_dir)
    
    def scan(
        self,
        niche_id: str,
        csv_path: Optional[str] = None,
        min_margin: float = 40.0,
        min_price: float = 100.0,
        max_price: float = 2000.0,
        min_rating: float = 3.5,
        limit: int = 100,
    ) -> ScanResult:
        """
        Escanea catalogo y filtra por nicho.
        """
        niche = NICHE_CATALOG.get(niche_id)
        if not niche:
            raise ValueError(f"Nicho no encontrado: {niche_id}")
        
        filters = get_niche_filters(niche_id)
        filters.update({
            "min_margin": min_margin,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,
        })
        
        # Load catalog
        csv_file = Path(csv_path) if csv_path else self.catalog_dir / "droppi_catalog.csv"
        
        if not csv_file.exists():
            # Return empty result if no catalog
            return ScanResult(
                niche_id=niche_id,
                scanned_at=datetime.now(timezone.utc).isoformat(),
                total_products=0,
                matched_products=0,
                filtered_products=0,
                filters=filters,
            )
        
        # Scan
        all_products = self._load_csv(csv_file)
        matched = self._match_keywords(all_products, niche)
        filtered = self._apply_filters(matched, filters)
        
        # Sort by match_score descending
        filtered.sort(key=lambda x: x.match_score, reverse=True)
        candidates = filtered[:limit]
        
        # Calculate stats
        avg_price = sum(p.price for p in candidates) / len(candidates) if candidates else 0
        avg_margin = sum(p.margin_percent for p in candidates) / len(candidates) if candidates else 0
        prices = [p.price for p in candidates]
        price_range = (min(prices), max(prices)) if prices else (0, 0)
        
        return ScanResult(
            niche_id=niche_id,
            scanned_at=datetime.now(timezone.utc).isoformat(),
            total_products=len(all_products),
            matched_products=len(matched),
            filtered_products=len(filtered),
            filters=filters,
            candidates=candidates,
            avg_price=avg_price,
            avg_margin=avg_margin,
            price_range=price_range,
        )
    
    def _load_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Carga CSV de catalogo."""
        products = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    products.append(row)
        except:
            pass
        return products
    
    def _match_keywords(self, products: List[Dict], niche: NicheProfile) -> List[ProductCandidate]:
        """Filtra productos que matchean keywords del nicho."""
        matched = []
        keywords = [k.lower() for k in niche.keywords]
        exclude = [k.lower() for k in niche.exclude_keywords]
        
        for p in products:
            title = p.get("title", "").lower()
            category = p.get("category", "").lower()
            description = p.get("description", "").lower()
            
            searchable = f"{title} {category} {description}"
            
            # Check excludes first
            if any(ex in searchable for ex in exclude):
                continue
            
            # Count keyword matches
            matches = [kw for kw in keywords if kw in searchable]
            if not matches:
                continue
            
            # Calculate match score
            match_score = len(matches) / len(keywords)
            
            # Parse fields
            try:
                price = float(p.get("price", 0))
                cost = float(p.get("cost", p.get("price", 0))) * 0.4  # Estimate if missing
                rating = float(p.get("rating", 0))
                reviews = int(p.get("reviews", 0))
                sales = int(p.get("sales", 0))
            except:
                continue
            
            candidate = ProductCandidate(
                product_id=p.get("id", p.get("product_id", "")),
                title=p.get("title", ""),
                category=p.get("category", ""),
                price=price,
                cost=cost,
                rating=rating,
                reviews=reviews,
                sales=sales,
                supplier_id=p.get("supplier_id", ""),
                supplier_name=p.get("supplier_name", ""),
                shipping_days=int(p.get("shipping_days", 7)),
                image_url=p.get("image_url", ""),
                images_count=int(p.get("images_count", 1)),
                keyword_matches=matches,
                match_score=match_score,
            )
            matched.append(candidate)
        
        return matched
    
    def _apply_filters(self, products: List[ProductCandidate], filters: Dict) -> List[ProductCandidate]:
        """Aplica filtros adicionales."""
        filtered = []
        
        min_margin = filters.get("min_margin", 40)
        min_price = filters.get("min_price", 100)
        max_price = filters.get("max_price", 2000)
        min_rating = filters.get("min_rating", 3.5)
        
        for p in products:
            if p.margin_percent < min_margin:
                continue
            if p.price < min_price or p.price > max_price:
                continue
            if p.rating > 0 and p.rating < min_rating:
                continue
            filtered.append(p)
        
        return filtered
    
    def quick_scan(self, niche_id: str, limit: int = 20) -> List[ProductCandidate]:
        """Escaneo rapido, retorna solo candidatos."""
        result = self.scan(niche_id, limit=limit)
        return result.candidates


def scan_niche(niche_id: str, limit: int = 50) -> ScanResult:
    """Helper para escaneo rapido."""
    scanner = CatalogScanner()
    return scanner.scan(niche_id, limit=limit)
