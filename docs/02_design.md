# Template Design Specification — RET-C2-623

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (in `src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph (Cat 2 — outer backbone + GraphNode + inner BaseGraph)
- **Three-Layer Separation**:
  - State: flat `State(AgentState)`; every agent-specific field `NotRequired`
  - Node: `FunctionNode.execute(self, state) -> dict` override only
  - Graph: `register_nodes()`; `add_edges()` NOT overridden (outer)

## Cat 2 Composition

Outer `Graph(AgentBaseGraph)` (`src/graph/graph.py`) with `EligibilityGraphNode` (a `GraphNode`,
same file) in the `main` slot, wrapping the inner `DomainWorkflowGraph` (`BaseGraph`,
`src/graph/domain_workflow_graph.py`). `gate-composition` requires this — a flat MainNode fails.

### Node Configuration (outer)

| Node | Responsibility | Output |
|------|---------------|--------|
| initialize | trust/session/schema | — |
| pre_process (QueryParse) | normalize query, extract facets, build validated_input JSON; S-2 credential/個人番号/injection scan | query_facets, validated_input |
| main (EligibilityGraphNode) | dispatch inner workflow, merge verdict/citations/disclaimer | verdict, citations, disclaimer |
| post_process (OutputValidate) | S-3 preservation gate: definitive verdict needs ≥1 policy + ≥1 statute citation + disclaimer, else downgrade | formatted_output |
| finalize | response_metadata | output |

### Inner workflow (DomainWorkflowGraph, BaseGraph)

```
START → policy_kb_retrieve → keihin_rule_retrieve → eligibility_assess → disclaimer_annotate → END
```

| Inner node | Responsibility |
|------------|---------------|
| policy_kb_retrieve | parse JSON user_input; hybrid retrieval (dense e5 + BM25) over internal policy KB; top_k=8, threshold=0.75 |
| keihin_rule_retrieve | dense retrieval over 景品表示法 rule KB (article metadata); top_k=6; below-threshold → insufficient-grounding flag |
| eligibility_assess | grounded verdict from both sets (temperature 0.0); insufficient grounding → needs-compliance-review (fail-safe) |
| disclaimer_annotate | append mandatory disclaimer + escalation pointer |

### Node mapping vs IDEA 6-node backbone

IDEA steps 2–7 (QueryParse → PolicyKBRetrieve → 景品法RuleRetrieve → EligibilityAssess →
DisclaimerAnnotate → OutputFormat) map to: QueryParse = outer pre_process; the four inner nodes;
OutputFormat = outer post_process (OutputValidate). IDEA step 1 (S-1/S-2) is realized via
`_extra_security_gate_input()` on QueryParse, not a separate node. A separate KB-ingestion
pipeline (deploy-time) is a service helper (`ingest`-style functions), not a runtime node.

### State Definition (agent-specific fields, all `NotRequired`)

| Field | Type | Purpose |
|-------|------|---------|
| query_text | str | parsed query (inner) |
| query_facets | dict | discount/campaign/product facets |
| policy_chunks | list[dict] | internal policy retrieval |
| statute_chunks | list[dict] | 景品法 retrieval |
| verdict | str | eligible / not-eligible / needs-compliance-review |
| rationale | str | grounded rationale |
| policy_citations | list[str] | policy § refs |
| statute_citations | list[str] | 景品法 article refs |
| disclaimer | str | mandatory compliance disclaimer |
| confidence | str | high/medium/low |

**State Constraints:** flat TypedDict; no credentials/JWT/Pydantic; InvocationContext via
`config["configurable"]` only.

## Security (5-layer)

- **S-1** — `required_trust_level = VERIFIED_EXTERNAL` explicit on every node, the outer
  main-slot `EligibilityGraphNode` included — left undeclared it inherits `ANONYMOUS`, and
  `gate-trust-level-check` does not scan `GraphNode` subclasses.
- **S-2** — `QueryParse._extra_security_gate_input()`: credential / 個人番号 / prompt-injection
  scan; clean business queries pass through. Credential-shaped content and prompt-injection
  are security failures: the gate returns `status=ERROR` and nothing is assessed. A
  personal-number identifier is masked by the framework's own S-2 scan before this node
  reads the request, so the question is answered with the number masked and it never
  reaches state or the output. This node's own check is a second line: an identifier that
  arrives unmasked is refused under the input policy as `error_code: REQUEST_NOT_ACCEPTED`,
  with a fixed notice that never names what matched. A request with no question in
  it is different: it is refused as a degraded run, returning SUCCESS with
  `error_code: EMPTY_INPUT` and no verdict, and the routing short-circuits the policy
  retrieval. The output is the reason alone, not the assessment shape with blank fields —
  an empty verdict inside that shape reads as "assessed, nothing found", which is the wrong
  thing to tell a caller asking whether a promotion is allowed.
- **S-3** — `OutputValidate._extra_security_gate_output()`: preservation variant — a definitive
  verdict must keep ≥1 policy + ≥1 statute citation + disclaimer, else downgrade to review.
- **S-4** — `emit_trace_event()` in every node (景品表示法 defense record); GraphNode emits in
  `extract_input()` / `merge_output()`.
- **S-5** — framework credential scan; secret `vector_store_api_key` via `ctx.secrets.require()`.

## Retrieval / grounding guardrails

- Hybrid (dense + BM25) for policy KB (product codes/campaign IDs need lexical match); dense for
  statute KB. `top_k` and `score_threshold` from `config/agent.yaml`.
- Insufficient grounding (missing either side, or below threshold) → `needs-compliance-review`,
  never a guessed verdict.
- Discount above the policy sign-off threshold → escalate to compliance.

## Outcome classification

Each way a run can end without an assessment falls into one class, and the class decides how it
is reported.

| Class | In this agent | Reported as |
|---|---|---|
| Security failure | Credential-shaped content or an instruction addressed to the agent — detected by the framework's gates or by this agent's own input scan | `status=ERROR`, `output=None` |
| Policy withholding (input) | A personal-number identifier that reaches this agent unmasked (the framework's S-2 scan masks the usual forms first; the question is then answered with the number masked) | `status=SUCCESS`, `error_code=REQUEST_NOT_ACCEPTED`, fixed notice |
| Caller-correctable | A request with no question in it | `status=SUCCESS`, `error_code=EMPTY_INPUT` |
| Fail-safe downgrade | A definitive verdict that lost its policy or statute citations | `status=SUCCESS`, verdict downgraded to needs-compliance-review |
| Optional dependency unavailable | The model is unreachable — it only refines the wording of the rationale | `status=SUCCESS` with the deterministic verdict and rationale |
| Invariant failure | State a preceding step guarantees is absent | `status=ERROR`; never represented as successful completion |

Credential-shaped content detected by baseline S-3 causes fail-closed termination:
`status=ERROR`, `output=None`. The template does not transform this terminal status to SUCCESS
and does not emit any source-derived response.

On a policy-withholding or caller-correctable run, `status=SUCCESS` means the agent finished
handling the request safely; it does not mean an assessment was returned. The notice is derived from
the `error_code` alone, so nothing from the request is echoed back.

## Import Isolation

- [x] No Level 0 (`agenticstar`) import. Import targets: `framework/`, `shared/`, `langgraph`, `src.`.

## Design Decision Record

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| L1 base type | AgentBaseGraph | Cat 2 backbone + GraphNode composition |
| Composition | GraphNode → inner BaseGraph | multi-step compliance workflow; `gate-composition` |
| Grounding | dual-KB + fail-safe downgrade | 景品表示法 defensibility; never guess |
| Retrieval | injectable retriever + fallback KB | runnable/testable without a vector store |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=ret`, `agent_name=ret-c2-623`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. The standalone entry point passes a client as `config["llm"]` only when the
provider client is available and all three values already resolve at startup; otherwise the key
stays unset and the graph runs its deterministic path. The Marketplace entry point cannot resolve
the values while the graph is built, so whenever the provider client is available it passes a
client that resolves them on each call. A value missing at that point makes the call fail, and the
model being optional here, the deterministic verdict and rationale stand; the failure is recorded
in the audit event. The manifest declares neither the three secrets nor the provider extra:
the model is optional, and declaring them would make it a startup prerequisite.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
