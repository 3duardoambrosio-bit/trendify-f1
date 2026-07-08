# V3GAP:E-01_aviso_privacidad_mx
# V3GAP:F-01_profeco_complete
# V3GAP:F-03_nom_verification_flag
# V3GAP:creative_review_no_prohibited_claims
"""
Mexico pre-launch compliance checklist (declarative stubs).
Not code features. Compliance gates verified manually before go-live.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class ComplianceItem:
    item_id: str
    description: str
    category: str
    requires_manual_verification: bool = True
    is_code_feature: bool = False

AVISO_PRIVACIDAD = ComplianceItem(
    item_id="E-01_aviso_privacidad_mx",
    description="Aviso de privacidad obligatorio. Debe referenciar Secretaria de Anticorrupcion (INAI disuelto marzo 2025). Derechos ARCO.",
    category="legal",
)
PROFECO_COMPLETE = ComplianceItem(
    item_id="F-01_profeco_complete",
    description="Politica de devoluciones 5 dias habiles (Art. 56 LFPC), garantia 90 dias (Art. 77), precios con IVA, canal de contacto.",
    category="legal",
)
NOM_VERIFICATION = ComplianceItem(
    item_id="F-03_nom_verification_flag",
    description="Flag de verificacion NOM por producto antes de publicar.",
    category="regulatory",
)
CREATIVE_REVIEW = ComplianceItem(
    item_id="creative_review_no_prohibited_claims",
    description="Revision manual de creativos: sin claims de salud, sin garantias absolutas, sin comparativas no demostrables.",
    category="content",
)

MX_PRELAUNCH_CHECKLIST: List[ComplianceItem] = [
    AVISO_PRIVACIDAD, PROFECO_COMPLETE, NOM_VERIFICATION, CREATIVE_REVIEW,
]

def get_pending_items() -> List[ComplianceItem]:
    return [i for i in MX_PRELAUNCH_CHECKLIST if i.requires_manual_verification]

def get_checklist_ids() -> List[str]:
    return [i.item_id for i in MX_PRELAUNCH_CHECKLIST]