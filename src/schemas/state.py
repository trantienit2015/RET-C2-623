"""AgentCore Platform v1.0 — State schema for RET-C2-623."""

# ADR-005: flat TypedDict only — no Pydantic (msgpack). Extend AgentState with
# agent-specific fields only; no credentials/secrets in State.

from typing import Any, NotRequired

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Pricing/eligibility Q&A agent state. Shared fields inherited from AgentState.
    Every agent-specific field is NotRequired (state-safety).
    """

    # Outcome marker. A run that completes without a verdict - a caller-correctable refusal or
    # a policy withholding - carries this code, and its output says why in wording
    # derived from the code alone (src/services/degradation.py). A security failure or
    # an internally inconsistent run ends as status=ERROR instead.
    error_code: NotRequired[str]

    # query
    query_text: NotRequired[str]
    query_facets: NotRequired[dict[str, Any]]

    # retrieval
    policy_chunks: NotRequired[list[dict[str, Any]]]
    statute_chunks: NotRequired[list[dict[str, Any]]]

    # assessment
    verdict: NotRequired[str]
    rationale: NotRequired[str]
    policy_citations: NotRequired[list[str]]
    statute_citations: NotRequired[list[str]]
    disclaimer: NotRequired[str]
    confidence: NotRequired[str]
