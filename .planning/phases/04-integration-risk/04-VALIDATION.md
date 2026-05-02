---
phase: 4
slug: integration-risk
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q --ignore=tests/e2e` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q --ignore=tests/e2e`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | RISK-01 | — | Margin bounds [0.15, 0.60] enforced | unit | `python -m pytest tests/unit/test_contracts.py -k margin` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | RISK-02 | — | Guardian veto blocks high-risk assets | unit | `python -m pytest tests/unit/test_contracts.py -k guardian` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | RISK-04 | — | HITL triggers on low conviction / high divergence | unit | `python -m pytest tests/unit/test_contracts.py -k hitl` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | PORTFOLIO-01, PORTFOLIO-03 | — | Sector limits and concentration caps respected | unit | `python -m pytest tests/unit/test_contracts.py -k optimizer` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 2 | PORTFOLIO-02 | — | Kelly criterion sizing within bounds | unit | `python -m pytest tests/unit/test_contracts.py -k kelly` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 2 | RISK-03 | — | Position sizing within [0.0, 0.10] | integration | `python -m pytest tests/unit/test_contracts.py -k position_size` | ❌ W0 | ⬜ pending |
| 04-05-01 | 05 | 3 | — | — | E2E smoke: structure + golden range assertions | e2e | `python -m pytest tests/e2e/test_live_smoke.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_contracts.py` — contract tests for all agent outputs, margin math, VeTO wiring
- [ ] `tests/e2e/test_live_smoke.py` — live smoke test with golden range assertions (D-17)
- [ ] Existing `conftest.py` and fixtures sufficient — no new framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live smoke test with real APIs | RISK-01 through RISK-04 | Requires Gemini API key and network access | Run `SMOKE_TICKER=AAPL python -m pytest tests/e2e/test_live_smoke.py -x --slow` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
