# synapse/discovery/niche_selector.py
"""
Niche Selector - Seleccion estrategica de nicho.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import json
from pathlib import Path


class NicheCategory(Enum):
    ELECTRONICS = "electronics"
    BEAUTY = "beauty"
    HOME = "home"
    FASHION = "fashion"
    FITNESS = "fitness"
    PETS = "pets"
    BABY = "baby"
    AUTOMOTIVE = "automotive"
    OUTDOOR = "outdoor"
    GADGETS = "gadgets"
    WELLNESS = "wellness"


class NicheRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CompetitionLevel(Enum):
    SATURATED = "saturated"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EMERGING = "emerging"


@dataclass
class NicheProfile:
    niche_id: str
    name: str
    category: NicheCategory
    subcategories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    avg_margin_percent: float = 50.0
    avg_price_range: Tuple[float, float] = (200, 800)
    competition: CompetitionLevel = CompetitionLevel.MEDIUM
    risk: NicheRisk = NicheRisk.MEDIUM
    primary_audience: str = "18-45 MX"
    gender_skew: str = "neutral"
    seasonality: str = "evergreen"
    peak_months: List[int] = field(default_factory=list)
    requires_certification: bool = False
    restricted_claims: List[str] = field(default_factory=list)
    opportunity_score: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["competition"] = self.competition.value
        d["risk"] = self.risk.value
        return d


NICHE_CATALOG: Dict[str, NicheProfile] = {
    "audio_personal": NicheProfile(
        niche_id="audio_personal",
        name="Audio Personal (Audifonos/Bocinas)",
        category=NicheCategory.ELECTRONICS,
        subcategories=["electronics/audio", "electronics/headphones"],
        keywords=["audifono", "auricular", "bocina", "speaker", "bluetooth", "tws", "earbuds"],
        exclude_keywords=["repuesto", "cable", "adaptador"],
        avg_margin_percent=55,
        avg_price_range=(150, 800),
        competition=CompetitionLevel.HIGH,
        risk=NicheRisk.LOW,
        opportunity_score=0.72,
    ),
    "smart_watches": NicheProfile(
        niche_id="smart_watches",
        name="Smartwatches y Wearables",
        category=NicheCategory.ELECTRONICS,
        subcategories=["electronics/wearables"],
        keywords=["smartwatch", "reloj inteligente", "fitness tracker", "smart band"],
        exclude_keywords=["correa", "mica", "cargador"],
        avg_margin_percent=50,
        avg_price_range=(300, 1500),
        competition=CompetitionLevel.HIGH,
        risk=NicheRisk.MEDIUM,
        opportunity_score=0.68,
    ),
    "phone_accessories": NicheProfile(
        niche_id="phone_accessories",
        name="Accesorios para Celular",
        category=NicheCategory.ELECTRONICS,
        subcategories=["electronics/phone_accessories"],
        keywords=["funda", "case", "cargador", "cable", "powerbank", "protector"],
        avg_margin_percent=60,
        avg_price_range=(50, 400),
        competition=CompetitionLevel.SATURATED,
        risk=NicheRisk.LOW,
        opportunity_score=0.55,
    ),
    "gaming_accessories": NicheProfile(
        niche_id="gaming_accessories",
        name="Accesorios Gaming",
        category=NicheCategory.ELECTRONICS,
        subcategories=["electronics/gaming"],
        keywords=["gaming", "gamer", "control", "mouse", "teclado", "headset", "rgb"],
        exclude_keywords=["consola"],
        avg_margin_percent=52,
        avg_price_range=(200, 1200),
        competition=CompetitionLevel.HIGH,
        risk=NicheRisk.MEDIUM,
        opportunity_score=0.65,
    ),
    "home_organization": NicheProfile(
        niche_id="home_organization",
        name="Organizacion del Hogar",
        category=NicheCategory.HOME,
        subcategories=["home/organization"],
        keywords=["organizador", "storage", "caja", "contenedor", "rack", "estante"],
        avg_margin_percent=58,
        avg_price_range=(100, 500),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        gender_skew="female",
        opportunity_score=0.70,
    ),
    "kitchen_gadgets": NicheProfile(
        niche_id="kitchen_gadgets",
        name="Gadgets de Cocina",
        category=NicheCategory.HOME,
        subcategories=["home/kitchen"],
        keywords=["cocina", "kitchen", "cortador", "pelador", "batidora", "utensilio"],
        exclude_keywords=["estufa", "refrigerador"],
        avg_margin_percent=55,
        avg_price_range=(80, 600),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        gender_skew="female",
        opportunity_score=0.68,
    ),
    "led_lights": NicheProfile(
        niche_id="led_lights",
        name="Iluminacion LED",
        category=NicheCategory.HOME,
        subcategories=["home/lighting"],
        keywords=["led", "luz", "lampara", "tira led", "rgb", "neon", "iluminacion"],
        avg_margin_percent=60,
        avg_price_range=(100, 500),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        opportunity_score=0.72,
    ),
    "skincare_tools": NicheProfile(
        niche_id="skincare_tools",
        name="Herramientas de Skincare",
        category=NicheCategory.BEAUTY,
        subcategories=["beauty/skincare"],
        keywords=["facial", "masajeador", "limpiador", "dermaroller", "gua sha", "skincare"],
        exclude_keywords=["crema", "serum"],
        avg_margin_percent=62,
        avg_price_range=(150, 700),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.MEDIUM,
        gender_skew="female",
        restricted_claims=["anti-aging", "cura"],
        opportunity_score=0.70,
    ),
    "hair_tools": NicheProfile(
        niche_id="hair_tools",
        name="Herramientas para Cabello",
        category=NicheCategory.BEAUTY,
        subcategories=["beauty/hair"],
        keywords=["cabello", "secadora", "plancha", "rizador", "cepillo", "alisador"],
        exclude_keywords=["shampoo", "tratamiento"],
        avg_margin_percent=55,
        avg_price_range=(200, 900),
        competition=CompetitionLevel.HIGH,
        risk=NicheRisk.LOW,
        gender_skew="female",
        opportunity_score=0.65,
    ),
    "home_fitness": NicheProfile(
        niche_id="home_fitness",
        name="Fitness en Casa",
        category=NicheCategory.FITNESS,
        subcategories=["fitness/equipment"],
        keywords=["fitness", "ejercicio", "gym", "pesas", "banda", "yoga", "mat"],
        exclude_keywords=["suplemento"],
        avg_margin_percent=52,
        avg_price_range=(150, 800),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        seasonality="seasonal",
        peak_months=[1, 2, 9],
        opportunity_score=0.67,
    ),
    "pet_accessories": NicheProfile(
        niche_id="pet_accessories",
        name="Accesorios para Mascotas",
        category=NicheCategory.PETS,
        subcategories=["pets/accessories"],
        keywords=["mascota", "perro", "gato", "collar", "correa", "cama", "juguete"],
        exclude_keywords=["alimento"],
        avg_margin_percent=58,
        avg_price_range=(100, 600),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        opportunity_score=0.71,
    ),
    "baby_gear": NicheProfile(
        niche_id="baby_gear",
        name="Articulos para Bebe",
        category=NicheCategory.BABY,
        subcategories=["baby/gear"],
        keywords=["bebe", "baby", "infantil", "portabebe", "biberon"],
        exclude_keywords=["formula", "panales"],
        avg_margin_percent=50,
        avg_price_range=(200, 1000),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.MEDIUM,
        gender_skew="female",
        requires_certification=True,
        opportunity_score=0.62,
    ),
    "car_accessories": NicheProfile(
        niche_id="car_accessories",
        name="Accesorios para Auto",
        category=NicheCategory.AUTOMOTIVE,
        subcategories=["automotive/accessories"],
        keywords=["auto", "carro", "coche", "soporte", "organizador", "camara"],
        exclude_keywords=["refaccion", "llanta"],
        avg_margin_percent=55,
        avg_price_range=(100, 700),
        competition=CompetitionLevel.MEDIUM,
        risk=NicheRisk.LOW,
        gender_skew="male",
        opportunity_score=0.66,
    ),
    "camping_gear": NicheProfile(
        niche_id="camping_gear",
        name="Equipo de Camping",
        category=NicheCategory.OUTDOOR,
        subcategories=["outdoor/camping"],
        keywords=["camping", "tienda", "linterna", "sleeping", "outdoor"],
        avg_margin_percent=55,
        avg_price_range=(200, 1200),
        competition=CompetitionLevel.LOW,
        risk=NicheRisk.LOW,
        gender_skew="male",
        seasonality="seasonal",
        peak_months=[3, 4, 7, 8, 11, 12],
        opportunity_score=0.68,
    ),
}


@dataclass
class NicheSelection:
    niche_id: str
    selected_at: str
    reason: str
    expected_margin: float
    expected_competition: str
    notes: str = ""


class NicheSelector:
    def __init__(self, config_dir: str = "data/config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.selection_file = self.config_dir / "niche_selection.json"
        self._current_selection: Optional[NicheSelection] = None
        self._load_selection()
    
    def _load_selection(self):
        if self.selection_file.exists():
            try:
                data = json.loads(self.selection_file.read_text(encoding="utf-8"))
                self._current_selection = NicheSelection(**data)
            except Exception:
                self._current_selection = None
    
    def _save_selection(self):
        if self._current_selection:
            self.selection_file.write_text(
                json.dumps(asdict(self._current_selection), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
    
    def list_all(self) -> List[NicheProfile]:
        return list(NICHE_CATALOG.values())
    
    def list_by_category(self, category: NicheCategory) -> List[NicheProfile]:
        return [n for n in NICHE_CATALOG.values() if n.category == category]
    
    def list_by_opportunity(self, min_score: float = 0.6) -> List[NicheProfile]:
        filtered = [n for n in NICHE_CATALOG.values() if n.opportunity_score >= min_score]
        return sorted(filtered, key=lambda x: x.opportunity_score, reverse=True)
    
    def list_low_risk(self) -> List[NicheProfile]:
        return [n for n in NICHE_CATALOG.values() if n.risk == NicheRisk.LOW]
    
    def get(self, niche_id: str) -> Optional[NicheProfile]:
        return NICHE_CATALOG.get(niche_id)
    
    def select(self, niche_id: str, reason: str, notes: str = "") -> NicheSelection:
        niche = self.get(niche_id)
        if not niche:
            raise ValueError(f"Nicho no encontrado: {niche_id}")
        self._current_selection = NicheSelection(
            niche_id=niche_id,
            selected_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            expected_margin=niche.avg_margin_percent,
            expected_competition=niche.competition.value,
            notes=notes,
        )
        self._save_selection()
        return self._current_selection
    
    def get_current(self) -> Optional[NicheSelection]:
        return self._current_selection
    
    def get_current_profile(self) -> Optional[NicheProfile]:
        if self._current_selection:
            return self.get(self._current_selection.niche_id)
        return None
    
    def clear_selection(self):
        self._current_selection = None
        if self.selection_file.exists():
            self.selection_file.unlink()
    
    def compare(self, niche_ids: List[str]) -> List[Dict[str, Any]]:
        result = []
        for nid in niche_ids:
            niche = self.get(nid)
            if niche:
                result.append({
                    "niche_id": nid,
                    "name": niche.name,
                    "opportunity_score": niche.opportunity_score,
                    "margin": niche.avg_margin_percent,
                    "competition": niche.competition.value,
                    "risk": niche.risk.value,
                })
        return sorted(result, key=lambda x: x["opportunity_score"], reverse=True)
    
    def recommend(self, max_risk: NicheRisk = NicheRisk.MEDIUM, min_margin: float = 50, avoid_saturated: bool = True) -> List[NicheProfile]:
        candidates = []
        risk_order = {NicheRisk.LOW: 0, NicheRisk.MEDIUM: 1, NicheRisk.HIGH: 2}
        for niche in NICHE_CATALOG.values():
            if risk_order[niche.risk] > risk_order[max_risk]:
                continue
            if niche.avg_margin_percent < min_margin:
                continue
            if avoid_saturated and niche.competition == CompetitionLevel.SATURATED:
                continue
            candidates.append(niche)
        return sorted(candidates, key=lambda x: x.opportunity_score, reverse=True)


def list_niches() -> List[str]:
    return list(NICHE_CATALOG.keys())


def get_niche_keywords(niche_id: str) -> List[str]:
    niche = NICHE_CATALOG.get(niche_id)
    return niche.keywords if niche else []


def get_niche_filters(niche_id: str) -> Dict[str, Any]:
    niche = NICHE_CATALOG.get(niche_id)
    if not niche:
        return {}
    return {
        "subcategories": niche.subcategories,
        "keywords_include": niche.keywords,
        "keywords_exclude": niche.exclude_keywords,
        "price_min": niche.avg_price_range[0],
        "price_max": niche.avg_price_range[1],
    }
