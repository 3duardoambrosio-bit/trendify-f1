"""Canonical marketing pattern blacklist shared by engine and UI.

This module is pure data. Keep it free of runtime behavior.
"""

from __future__ import annotations


GENERIC_BLACKLIST: tuple[str, ...] = (
    'el mejor producto',
    'calidad garantizada',
    'ideal para todos',
    'compra ahora',
    'no te lo pierdas',
    'solución perfecta',
    'solucion perfecta',
    'producto innovador',
    'producto increíble',
    'producto increible',
    'revolucionario',
    'dile adiós',
    'dile adios',
    'lo que usan los que saben',
    'los que saben',
    'realmente funciona',
    'desorden y la incomodidad',
    'la alternativa inteligente que tu cartera',
    'por qué pagar más si',
    'por que pagar mas si',
    'mientras otros usan genéricos',
    'mientras otros usan genericos',
    'el detalle perfecto para quien tiene todo',
    'para los que no se conforman',
    'si la frustración de no tener',
    'si la frustracion de no tener',
    'no tener la solución correcta',
    'no tener la solucion correcta',
)


__all__ = ["GENERIC_BLACKLIST"]
