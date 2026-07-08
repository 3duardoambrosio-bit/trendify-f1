# Backlog post UI

## BACKLOG_P1 — sincronizar NPC blacklist UI con motor

Origen: auditoría Claude A8-R55 sobre HEAD `f878e29`.

Problema:
La UI `synapse/ui/read_model.py` tiene una blacklist NPC propia para marcar hooks con `[NPC_TEMPLATE]`, pero puede subdetectar plantillas que el motor ya reconoce.

Plantillas mencionadas por auditoría como faltantes en UI:
- "la alternativa inteligente que tu cartera"
- "mientras otros usan genéricos"
- "mientras otros usan genericos"
- "el detalle perfecto para quien tiene todo"
- "para los que no se conforman"

Riesgo:
False-negative visual. El operador puede ver hooks sin `[NPC_TEMPLATE]` aunque sí sean plantillas genéricas.

Estado:
No bloquea A8-R55. Resolver antes de depender de la UI para evaluación creativa seria o antes de operar productos nuevos.
