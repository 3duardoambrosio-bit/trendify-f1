# V3GAP:E-02_checkout_mx_fields

# V3GAP:E-02_checkout_mx_fields

from __future__ import annotations

"""
Checkout MX Fields — E-02.

Validaciones y normalización de checkout para México:
- Teléfono: "+52" + 10 dígitos
- Código postal: 5 dígitos
- RFC: opcional, validación de formato si se proporciona
- Uso CFDI: catálogo SAT (subset operativo)
- Estado: catálogo de estados mexicanos (32)

__MARKER__ embedded in module constant below.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import deal

__MARKER__ = "SESSION_S11_checkout_mx_2026-03-02"

log = logging.getLogger(__name__)

_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")
_DIGITS_RE = re.compile(r"\D+")

MX_ESTADOS: Dict[str, str] = {
    "AGUASCALIENTES": "AGU",
    "BAJA CALIFORNIA": "BCN",
    "BAJA CALIFORNIA SUR": "BCS",
    "CAMPECHE": "CAM",
    "CHIAPAS": "CHP",
    "CHIHUAHUA": "CHH",
    "CIUDAD DE MEXICO": "CDMX",
    "COAHUILA": "COA",
    "COLIMA": "COL",
    "DURANGO": "DUR",
    "GUANAJUATO": "GUA",
    "GUERRERO": "GRO",
    "HIDALGO": "HID",
    "JALISCO": "JAL",
    "MEXICO": "MEX",
    "MICHOACAN": "MIC",
    "MORELOS": "MOR",
    "NAYARIT": "NAY",
    "NUEVO LEON": "NLE",
    "OAXACA": "OAX",
    "PUEBLA": "PUE",
    "QUERETARO": "QUE",
    "QUINTANA ROO": "ROO",
    "SAN LUIS POTOSI": "SLP",
    "SINALOA": "SIN",
    "SONORA": "SON",
    "TABASCO": "TAB",
    "TAMAULIPAS": "TAM",
    "TLAXCALA": "TLA",
    "VERACRUZ": "VER",
    "YUCATAN": "YUC",
    "ZACATECAS": "ZAC",
}

CFDI_USAGE: Dict[str, str] = {
    "G01": "Adquisicion de mercancias",
    "G03": "Gastos en general",
    "S01": "Sin efectos fiscales",
    "I01": "Construcciones",
    "I02": "Mobiliario y equipo de oficina por inversiones",
    "D01": "Honorarios medicos, dentales y gastos hospitalarios",
}

@deal.pre(lambda raw: isinstance(raw, str) and raw.strip() != "")
@deal.post(lambda result: isinstance(result, str) and result.startswith("+52") and len(result) == 13)
def normalize_mx_phone(raw: str) -> str:
    s = raw.strip()
    digits = _DIGITS_RE.sub("", s)
    # Si viene con +52, suele quedar como 5255...
    if digits.startswith("52") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        raise ValueError("invalid_mx_phone_length")
    return "+52" + digits

def validate_mx_postal_code(code: str) -> bool:
    if not isinstance(code, str):
        return False
    c = code.strip()
    return len(c) == 5 and c.isdigit()

def validate_rfc(rfc: str) -> bool:
    if not isinstance(rfc, str):
        return False
    x = rfc.strip().upper()
    if len(x) not in (12, 13):
        return False
    return bool(_RFC_RE.match(x))

@dataclass(frozen=True)
class CheckoutMxValidator:
    def validate_shipping_address(self, address: Dict) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        postal = (address or {}).get("postal_code") or (address or {}).get("zip") or ""
        if not validate_mx_postal_code(str(postal)):
            errors.append("invalid_postal_code")

        state = (address or {}).get("state") or (address or {}).get("province") or ""
        state_norm = str(state).strip().upper()
        if state_norm not in MX_ESTADOS:
            errors.append("invalid_state")

        phone = (address or {}).get("phone") or ""
        try:
            normalize_mx_phone(str(phone))
        except Exception as e:
            errors.append(f"invalid_phone:{type(e).__name__}")

        return (len(errors) == 0, errors)

    def validate_billing_info(self, billing: Dict) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        rfc = (billing or {}).get("rfc")
        if rfc is not None and str(rfc).strip() != "":
            if not validate_rfc(str(rfc)):
                errors.append("invalid_rfc")
        return (len(errors) == 0, errors)
