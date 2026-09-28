"""AgentCore Platform v1.0 — PolicyKBRetrieve (inner, first) for RET-C2-623."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.degradation import EMPTY_INPUT

from src.services.pricing_qa_service import retrieve_policy


class PolicyKBRetrieveNode(FunctionNode):
    """First inner node — parse the JSON payload and hybrid-retrieve internal policy KB."""

    # S-1: read-only retrieval over tenant policy KB.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, retriever: Any | None = None, top_k: int = 8, score_threshold: float = 0.75):
        self._retriever = retriever
        self._top_k = top_k
        self._score_threshold = score_threshold

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (ValueError, TypeError):
            payload = {}
        query = (payload.get("query") or "").strip() if isinstance(payload, dict) else ""
        if not query:
            emit_trace_event(
                "policy_retrieve_failed",
                {"correlation_id": state.get("correlation_id"), "reason": "no_query"},
                state,
            )
            # The subgraph is seeded with the request payload alone, so this node cannot
            # tell "the outer step already refused" from "upstream dropped the field".
            # Both readings point at the same thing the caller can do.
            return {"error_code": EMPTY_INPUT, "status": AgentStatus.SUCCESS.value}

        chunks = retrieve_policy(
            query, retriever=self._retriever, top_k=self._top_k, score_threshold=self._score_threshold
        )
        emit_trace_event(
            "policy_retrieved",
            {"correlation_id": state.get("correlation_id"), "n_chunks": len(chunks)},
            state,
        )
        return {"query_text": query, "policy_chunks": chunks, "status": AgentStatus.SUCCESS.value}
