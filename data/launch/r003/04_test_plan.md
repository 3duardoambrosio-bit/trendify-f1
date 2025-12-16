# r003 — Test Plan (Fase 1)

## Objetivo
Validar si puede sostener ROAS >= 1.0 con spend suficiente.

## Presupuesto sugerido (con  total)
- Reserve intocable: 45
- Learning: 90
- Operational: 165

Para iniciar:
- r003: 60 (learning)
- r004: 30 (learning backup)

## Señales de continuar / pausar / matar
- Spend < 10: CONTINUE (insufficient_data)
- ROAS < 0.7 con spend >= 10: KILL
- 0.7 <= ROAS < 1.0 con spend >= 10: PAUSE
- ROAS >= 1.0 con spend >= 10: CONTINUE
- ROAS >= 1.3 con spend >= 30: candidato a SCALE

## Checklist antes de correr ads
- Video prueba potencia real (NO claims inflados sin prueba)
- Copy transparente batería/uso turbo
- Política de devoluciones clara

