from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class ProductSource(str, Enum):
    DROPPI = "droppi"
    CSV = "csv"


class Decision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ProductSchema(BaseModel):
    product_id: str = Field(..., description="Identificador único del producto")
    external_id: str = Field(..., description="ID de Droppi/CSV")
    name: str = Field(..., min_length=1, description="Nombre del producto")
    description: Optional[str] = Field(None, description="Descripción del producto")
    category: str = Field(..., description="Categoría del producto")
    cost_price: float = Field(..., description="Precio de costo", ge=0)
    sale_price: float = Field(..., description="Precio de venta", ge=0)
    margin_percentage: Optional[float] = Field(
        None, description="Margen calculado (opcional)"
    )
    supplier: Optional[str] = Field(None, description="Proveedor")
    trust_score: Optional[float] = Field(
        None, description="Puntuación de confianza (0-10)"
    )
    suspicion_flags: List[str] = Field(
        default_factory=list, description="Banderas de sospecha"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadatos adicionales"
    )
    source: ProductSource = Field(..., description="Fuente del producto")
    created_at: Optional[str] = Field(None, description="Fecha de creación")
    updated_at: Optional[str] = Field(None, description="Fecha de actualización")


class BuyerDecisionSchema(BaseModel):
    decision_id: str = Field(..., description="Identificador único de la decisión")
    product_id: str = Field(..., description="ID del producto evaluado")
    decision: Decision = Field(..., description="Decisión tomada")
    reasons: List[str] = Field(..., description="Razones de la decisión")
    scores: Dict[str, float] = Field(..., description="Puntuaciones calculadas")
    model_used: Optional[str] = Field(None, description="Modelo de IA utilizado")
    evaluated_at: str = Field(..., description="Fecha de evaluación")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadatos adicionales"
    )
