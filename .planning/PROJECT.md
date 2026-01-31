# AI-Investment Swarm

## What This Is

Sistema multi-agente de inversión basado en Value Investing que analiza activos financieros mediante un flujo dialéctico de 10 agentes especializados. Diseñado para ser completamente auditable y transparente, cumpliendo con el EU AI Act como sistema de soporte a la decisión. Orientado a inversores que buscan trazabilidad completa del razonamiento detrás de cada recomendación.

## Core Value

Transparencia total: cada decisión de inversión debe ser trazable, explicable y auditable — el usuario entiende exactamente por qué el sistema recomienda (o no) un activo.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Orquestación de 10 agentes mediante LangGraph con grafo de estados auditable
- [ ] Capa 1 (Contexto): Macro Oracle y Sentiment Agent para régimen de mercado
- [ ] Capa 2 (Selección): Value Hunter (EPV/Graham) y Strategist (VeTO/VoMC)
- [ ] Capa 3 (Fricción): Bear, Historian y Guardian para validación crítica
- [ ] Capa 4 (Orquestación): Judge (consenso) y Optimizer (sizing de posiciones)
- [ ] Capa 5 (Ejecución): Trader para simulación de operaciones
- [ ] Knowledge base con RAG sobre bibliografía financiera (papers, libros, PDFs)
- [ ] Evaluación de calidad de retrieval con RAGAs/DeepEval
- [ ] Human-in-the-Loop dinámico: incertidumbre, desacuerdo entre agentes, anomalías
- [ ] Integración con APIs de datos financieros (fuentes por definir)
- [ ] Sistema de fallback para APIs con caché y escalamiento a HITL
- [ ] Backtesting y paper trading (simulación 6 meses)
- [ ] Generación de recomendaciones con explicabilidad completa
- [ ] Dashboard con visualización del razonamiento de cada agente
- [ ] Vistas por categoría de análisis
- [ ] Interfaz para intervención HITL
- [ ] Cumplimiento EU AI Act (sistema de soporte a decisión, transparencia algorítmica)

### Out of Scope

- Ejecución real de operaciones contra brokers — v1 es solo simulación y recomendaciones
- Trading de alta frecuencia — el sistema es para análisis fundamental, no HFT
- Aplicación móvil nativa — webapp es suficiente para MVP

## Context

**Origen:** Trabajo de Fin de Máster con deadline en junio 2026 (~5 meses)

**Fundamentos teóricos ya definidos:**
- Value Investing: Benjamin Graham, Bruce Greenwald (EPV)
- Ciclos económicos: Ray Dalio
- Mercados adaptativos: Andrew Lo
- Viabilidad estratégica: Modelos VeTO y VoMC (Cabanelas, 2015)
- Detección de fraude: Altman Z-Score, Beneish M-Score
- Valoración histórica: Robert Shiller

**Arquitectura de agentes definida:**
- 5 capas con flujo dialéctico (Propuesta → Antítesis → Síntesis)
- Cada agente tiene State Schema y Log de Explicabilidad definidos
- Lógica de juicio especificada para cada agente

**Bibliografía disponible:** Papers académicos, PDFs, libros — se cargarán manualmente a la knowledge base.

## Constraints

- **Presupuesto**: Mínimo — APIs gratuitas o muy económicas (Google AI, Supabase free tier)
- **Timeline**: MVP funcional para junio 2026
- **Regulatorio**: Debe cumplir EU AI Act como sistema de soporte a decisión
- **Escalabilidad**: Arquitectura debe permitir escalar post-MVP sin reescribir

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph sobre n8n | Agentes con lógica compleja (Monte Carlo, fuzzy logic, debates) requieren código, no nodos visuales. LangGraph provee grafo de estados auditables nativamente. | — Pending |
| Python como lenguaje principal | Ecosistema financiero maduro (pandas, numpy), LangGraph es Python-native, velocidad de desarrollo para MVP. Performance se optimiza después si es necesario. | — Pending |
| Google AI para LLMs | Tier gratuito disponible, suficiente para MVP | — Pending |
| Supabase para base de datos | Tier gratuito, PostgreSQL con vector search para RAG | — Pending |
| Simulación antes de ejecución real | v1 valida el sistema con backtesting y paper trading antes de arriesgar capital real | — Pending |

---
*Last updated: 2026-01-31 after initialization*
