# Test Specification

## Test Strategy
- Coverage target: all business-logic paths (per-node success + error/edge) plus one
  full-graph integration; hard % threshold enforced by the CI gate.
- Test types: Unit (per node) / Integration (full outer graph compile+invoke) / Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations (S-5 enforcement is done in CI) | |
| TC-04 | InvocationContext via configurable only | Direct access raises error | |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | Domain-specific input checks execute correctly (e.g. PII scan on additional fields, consent validation, business rules) | Hook body non-trivial |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | Domain-specific output checks execute correctly (e.g. nested credential scan, PII re-check, content filtering, preservation verification) | Hook body non-trivial |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | |
| PB-3 | Level 2 → External service | Real external service connection | Data retrieved | |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | |

## Business Logic Tests (tests/unit/test_nodes.py, tests/integration/test_graph.py)

| TC-ID | Test | Expected Result |
|-------|------|----------------|
| BL-01 | QueryParse extracts discount facet | SUCCESS, discount_pct=40 |
| BL-02 | QueryParse refuses an empty request | degraded SUCCESS carrying `error_code: EMPTY_INPUT`, no verdict |
| BL-03 | S-2 rejects prompt-injection and credentials; refuses an unmasked personal number by policy (gate called directly) | injection / credentials → `status=ERROR` (security failure); personal number → marked `REQUEST_NOT_ACCEPTED`, `execute()` returns a fixed notice without parsing the request |
| BL-04 | S-2 passes clean business query | pass-through |
| BL-05 | PolicyKBRetrieve fallback match | ≥1 chunk |
| BL-06 | KeihinRuleRetrieve match / no-match | chunks / empty |
| BL-07 | EligibilityAssess eligible when grounded | verdict=eligible + citations |
| BL-08 | EligibilityAssess needs-review when ungrounded | needs-compliance-review |
| BL-09 | EligibilityAssess review over 40% threshold | needs-compliance-review |
| BL-10 | DisclaimerAnnotate appends disclaimer / escalation | disclaimer present |
| BL-11 | OutputValidate downgrades missing citations | needs-compliance-review |
| BL-12 | S-3 gate downgrades dropped citations | needs-compliance-review |
| BL-13 | Full graph success | SUCCESS, ≥5 node_history, verdict=eligible |
| BL-14 | Full graph empty input degrades | SUCCESS; `output` is the caller-facing reason, never a verdict |
| BL-15 | The refused request never reaches the policy retrieval | SUCCESS with the same reason; the retriever is never called |
| BL-16 | Full graph prompt-injection input | `status=ERROR`, `output=None` (security failure) |
| BL-17 | The refusal is reported as a refusal, not a blank verdict | `output` is the reason alone, not the assessment shape with empty fields |
| BL-18 | Full graph with a personal number in the question | `status=SUCCESS`; the number is masked before the agent reads it and appears nowhere in the result |

### How each outcome is reported

A request with no question in it is refused as `EMPTY_INPUT`. A personal-number identifier
is masked by the framework's S-2 scan before this agent reads the request, so the question
is answered with the number masked (BL-18); one that arrives unmasked is refused by this
agent's own check as `REQUEST_NOT_ACCEPTED` (BL-03), in wording that never names what
matched.
`status=SUCCESS` there means the request was handled safely, not that an assessment was
returned. The preservation gate is not a refusal at all — a definitive verdict that lost its
citations is downgraded to needs-compliance-review, which already reaches the caller intact.

Credential-shaped content and prompt-injection (BL-03, BL-16) are security failures and an
invariant failure is a defect: all end as `status=ERROR` and are never represented as a
successful completion.

## Test Execution Summary
- Local: 20 unit + integration tests pass with the framework package on `PYTHONPATH`.
- PB-6 (`test_pb_invoke_order.py`) and `test_import_isolation.py` are the CI gate of record.
  PB-6 is skipped/adapted locally by design — the local framework mirror lacks the
  `emit_trace_event` stub on `base_node`, so the order assertion cannot run there; this is an
  expected local adaptation, not a test failure. Both pass under the CI wheel
  (`agenticstar-agentcore==1.0.0`) on Linux/UTF-8.

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |

### TC-DEP-03 Optional model on the deployment path — `tests/integration/test_deployment_without_llm_credentials.py`

| Case | Expected |
|---|---|
| The per-call client the Marketplace entry point injects, with none of the three connection values supplied | the call is attempted, cannot resolve its values, and the run completes with the same verdict, citations and rationale as a run with no model |
| The manifest | does not declare the three connection values or the provider extra as startup requirements |
