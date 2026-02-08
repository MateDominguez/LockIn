# AI-Investment Swarm

## What This Is

Sistema multi-agente de inversión que combina Value Investing clásico (Graham) con análisis prospectivo (VeTO/VoMC) mediante un enjambre de 7 agentes especializados orquestados con LangGraph. El sistema analiza carteras proporcionadas por el usuario a través de un flujo dialéctico (Bull vs Bear → Síntesis Bayesiana) para generar recomendaciones explicables y auditables. Diseñado como "caja de cristal" (no caja negra), cumpliendo con el EU AI Act como sistema de soporte a la decisión. Nivel 4 de autonomía: la IA razona y propone, el humano decide y ejecuta.

**Filosofía de inversión híbrida:**
- **Graham (base clásica):** Margen de seguridad, calidad de balance, poder de beneficios (EPV)
- **VeTO (prospectiva):** Calidad de ejecución y talento organizativo inferido de comunicaciones corporativas
- **VoMC (operativa):** Fragilidad operativa y capacidad de sostener crecimiento sin deterioro financiero
- **Tesis:** Solo recomendar cuando convergen valoración razonable + fortaleza financiera + capacidad de ejecución + riesgo controlado

## Core Value

**Transparencia total:** Cada decisión de inversión debe ser trazable, explicable y auditable. El usuario entiende exactamente por qué el sistema recomienda (o no) un activo, qué evidencias respaldan la tesis, qué riesgos se detectaron, y cómo se sintetizó el debate entre agentes.

## Agent Architecture (v1)

**7 agentes especializados con flujo dialéctico:**

1. **Macro Oracle** — Detecta régimen de mercado (Dalio cycles) y establece contexto para valuación
2. **Value Hunter (Bull)** — Análisis fundamental con EPV/EVA/RIM, construye tesis alcista con distribución de valor
3. **Strategist** — Análisis cualitativo simplificado (VeTO v1: sentiment + keywords de earnings calls/news)
4. **Bear** — Devil's advocate con mandato de "short case", desafía tesis alcista en iteraciones dialécticas
5. **Guardian** — Risk management con poder de veto (Altman Z-Score, Beneish M-Score, VoMC), dimensionamiento inicial
6. **Judge** — Síntesis Bayesiana de distribuciones Bull/Bear, resuelve conflictos, produce recomendación por activo
7. **Optimizer** — Construcción de cartera con Kelly Criterion, diversificación sectorial, threshold rebalancing

**Flujo dialéctico (por activo):**
```
Macro Oracle (contexto) → Value Hunter (tesis inicial) ⇄ Bear (desafío + contra-tesis)
→ Strategist (señales cualitativas) → Guardian (validación riesgo + veto?)
→ Judge (síntesis Bayesiana) → Optimizer (sizing + portfolio)
```

**Iteración Bull-Bear:** Mínimo 1 iteración dialéctica donde Bear desafía y Bull refina su tesis antes de síntesis.

**Deferred to v2:**
- Chartist (timing técnico)
- Historian (contexto histórico de valuación)
- Full VeTO scoring (NLP complejo con clustering semántico)
- Trader (no hay ejecución, usuario es el trader)
- Active screening (v1 analiza watchlist del usuario, no busca en SP500 completo)

## Requirements

### Validated

(None yet — ship to validate)

### Active (v1)

**Infrastructure:**
- [ ] LangGraph StateGraph con 7 agentes y estado compartido auditable
- [ ] Checkpointing PostgreSQL para HITL (Supabase)
- [ ] RAG con Parent Document Retriever sobre bibliografía financiera
- [ ] RAGAs/DeepEval para validación de faithfulness (>95% target)

**Data Layer:**
- [ ] Integración yfinance + FRED (single source v1, no fallback multi-source)
- [ ] Data validation: point-in-time wrapper, outlier detection, cross-check vs SEC
- [ ] Historical fundamentals storage en PostgreSQL
- [ ] Data lineage: cada claim enlaza a fuente primaria (SEC filing + section)

**Agent Implementation:**
- [ ] Macro Oracle: FRED + regime detection (Dalio framework)
- [ ] Value Hunter: EPV (mature), EVA (tech), RIM (financials) con SBC adjustments
- [ ] Strategist: Simplified VeTO (keyword extraction + sentiment, NLP básico)
- [ ] Bear: Dialectical challenger con distribución de valor pesimista
- [ ] Guardian: Altman Z-Score, Beneish M-Score, VoMC fragility analysis
- [ ] Judge: Bayesian consensus con convergence/divergence analysis
- [ ] Optimizer: Kelly Criterion sizing, sector diversification (límites 30-35%)

**Risk Management:**
- [ ] Adaptive margin of safety (base 25-30% + ajustes dinámicos por riesgo)
- [ ] Guardian veto logic (Z<1.1, M>-2.22+flags, Debt/EBITDA>3x+fragility)
- [ ] Position limits: max 10-12% per asset, sector limits
- [ ] HITL triggers: conviction<50%, divergence>30%, multiple red flags, Guardian veto

**Validation & Testing:**
- [ ] Backtesting engine con walk-forward analysis
- [ ] Paper trading simulation (6 months, sin ejecución real)
- [ ] Multi-regime backtesting
- [ ] Case studies: defensive (Coca-Cola) vs growth (Alphabet)

**Interface:**
- [ ] Streamlit dashboard con visualización de razonamiento por agente
- [ ] Panel de consenso multi-agente (Bull vs Bear synthesis)
- [ ] Audit trail browser (trazabilidad end-to-end)
- [ ] HITL approval interface
- [ ] Data viewer con enlaces a SEC filings

**Compliance:**
- [ ] EU AI Act: risk management documentation, data governance, logging
- [ ] Glass box transparency: fuentes, supuestos, límites, incertidumbre
- [ ] Disclaimers: "software de soporte B2B", no recomendaciones 1:1

### Out of Scope (v1)

- Ejecución real de operaciones — v1 solo genera recomendaciones, usuario ejecuta
- Trading de alta frecuencia — sistema es para análisis fundamental
- Aplicación móvil — webapp Streamlit suficiente para MVP
- Active stock screening — v1 analiza watchlist del usuario, no busca en SP500
- Technical timing (Chartist) — pure fundamental approach en v1
- Full VeTO NLP model — v1 usa sentiment + keywords simplificado
- Multi-source data fallback — v1 solo yfinance+FRED, fallback en v2

## Constitution (Reglas No Negociables)

**Principios del sistema que todos los agentes deben obedecer:**

1. **Regla de Evidencia:** Cualquier afirmación financiera relevante debe enlazar a fuente primaria o dato estructurado (SEC filing + section/page)

2. **Regla Anti-Alucinación:** Si el RAG no encuentra evidencia suficiente, el sistema responde "insuficiente evidencia", nunca inventa datos

3. **Regla de Veto por Riesgo:** Guardian puede bloquear una propuesta aunque todos los demás agentes voten a favor

4. **Regla de Coherencia:** Si hay contradicción entre agentes (ej: Bull optimista vs Guardian pesimista), Judge fuerza reconciliación o escala a HITL

5. **Conservadurismo ante Incertidumbre:** Si falta evidencia o hay baja confianza, el sistema degrada a "no decisión" (no fuerza recomendación)

6. **Human-in-the-Loop Obligatorio:** Ninguna acción con impacto real se ejecuta sin validación humana

## Context

**Origen:** Trabajo de Fin de Máster con deadline junio 2026 (~5 meses)

**Propósito triple:**
- TFM académico (rigor teórico, bibliografía)
- Guía de desarrollo (arquitectura, estados, lógica de grafos)
- Plan de negocio SaaS (go-to-market, compliance, B2B positioning)

**Fundamentos teóricos:**
- **Value Investing:** Benjamin Graham (Security Analysis), Bruce Greenwald (EPV)
- **Bayesian Inference:** Framework probabilístico para consenso (Thomas Bayes, Nate Silver)
- **Ciclos económicos:** Ray Dalio (All Weather, regime detection)
- **VeTO (Viabilidad Estratégica):** Talento Organizativo y Capacidad de Absorción (Cabanelas 2024)
- **VoMC (Viabilidad Operativa):** Fragilidad operativa y apalancamiento (Cabanelas 2024)
- **Detección de fraude:** Altman Z-Score (1968), Beneish M-Score (1999)
- **Quality screening:** Piotroski F-Score (2000), Greenblatt Magic Formula (2005)
- **Economic Value Added:** Stewart/McKinsey (EVA para tech con capitalización de R&D)
- **Portfolio theory:** Kelly Criterion adaptado (1956)

**Arquitectura:**
- 7 agentes orquestados con LangGraph StateGraph
- Flujo dialéctico con iteración Bull-Bear (mínimo 1 ida/vuelta)
- Síntesis Bayesiana (no voting ni promedio simple)
- Estado compartido con audit trail completo
- Checkpointing PostgreSQL para HITL interruptions

**Bibliografía disponible:** Papers académicos, 10-K/10-Qs, libros financieros — RAG con Parent Document Retriever

## Constraints

- **Presupuesto:** Mínimo — Google AI free tier (Gemini 1500 req/day), Supabase free tier (500MB, pgvector), yfinance/FRED (gratis)
- **Timeline:** MVP funcional para junio 2026 (~18 semanas de desarrollo)
- **Regulatorio:** EU AI Act compliance (high-risk system classification), CNMV/ESMA positioning como "B2B decision support software"
- **Escalabilidad:** Arquitectura debe permitir v2 sin reescribir (agregar Chartist, Historian, Full VeTO, active screening)
- **Scope:** v1 analiza watchlist del usuario, no busca activamente en SP500 (deferred to v2)

## Key Decisions

| Decision | Rationale | Outcome | Date |
|----------|-----------|---------|------|
| **7 agentes para v1 (no 10)** | Strategist incluido (core para VeTO), Chartist/Historian/Trader deferred. Balance entre ambición y timeline. | ✓ Decided | 2026-02-08 |
| **Bayesian synthesis (no voting)** | Voting simple ignora incertidumbre y confianza. Bayesian synthesis pondera distribuciones por convergencia, calidad de datos, y track record. | ✓ Decided | 2026-02-08 |
| **Bull-Bear dialectic con iteración** | Mínimo 1 ida/vuelta: Bear desafía → Bull refina → mejor tesis. Evita consenso superficial, fuerza "extreme friction". | ✓ Decided | 2026-02-08 |
| **LangGraph sobre n8n** | Agentes con lógica compleja (Bayesian math, dialéctica, veto logic) requieren código. LangGraph provee StateGraph auditable nativamente. | ✓ Decided | 2026-01-31 |
| **Python como lenguaje principal** | Ecosistema financiero maduro (pandas, numpy, scipy), LangGraph Python-native, RAG libraries disponibles. | ✓ Decided | 2026-01-31 |
| **Google AI (Gemini) para LLMs** | Free tier 1500 req/day suficiente para MVP. Fallback a OpenAI si rate limits son problema en Phase 3. | ✓ Decided | 2026-01-31 |
| **Supabase para DB + RAG** | Free tier 500MB, PostgreSQL con pgvector para embeddings, checkpointing para HITL. | ✓ Decided | 2026-01-31 |
| **yfinance + FRED (single source)** | Simplicidad en v1. Multi-source fallback (Alpha Vantage, FMP) deferred to v2. | ✓ Decided | 2026-02-08 |
| **Simplified VeTO en v1** | Full VeTO NLP (clustering semántico, absorption capacity model) es complejo (3-4 semanas). v1 usa keyword extraction + sentiment. Full model en v2. | ✓ Decided | 2026-02-08 |
| **No technical timing (Chartist)** | Pure fundamental approach en v1. Technical timing no es core value proposition y agrega complejidad. Deferred to v2. | ✓ Decided | 2026-02-08 |
| **User is the trader (no Trader agent)** | Sistema genera recomendaciones, no ejecuta. Alineado con EU AI Act positioning (decision support, not automated trading). | ✓ Decided | 2026-02-08 |
| **Watchlist only (no screening)** | v1 analiza cartera proporcionada por usuario. Active screening en SP500 completo deferred to v2 (agrega complejidad de data pipeline). | ✓ Decided | 2026-02-08 |
| **Guardian veto power** | Separación de concerns: otros agentes recomiendan, Guardian bloquea riesgos inaceptables. Evita "consensus bias" donde todos votan sí por presión grupal. | ✓ Decided | 2026-02-08 |
| **Adaptive margin of safety** | Margen fijo (30%) es demasiado rígido. Margen dinámico (base + ajustes por riesgo) refleja realidad de varianza en calidad/riesgo entre empresas. | ✓ Decided | 2026-02-08 |
| **Streamlit para UI** | Prototipado rápido, suficiente para MVP TFM. Dashboard profesional en v2 si se convierte en SaaS. | ✓ Decided | 2026-02-08 |
| **Backtesting antes de paper trading** | Validar lógica con datos históricos (walk-forward, multi-regime) antes de simular en tiempo real. Evita desperdiciar 6 meses en sistema roto. | ✓ Decided | 2026-02-08 |

---
*Last updated: 2026-02-08 after agent architecture finalization*
