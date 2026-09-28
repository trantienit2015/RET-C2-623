"""AgentCore Platform v1.0 — KeihinRuleRetrieve (inner) for RET-C2-623."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.pricing_qa_service import retrieve_statute


class KeihinRuleRetrieveNode(FunctionNode):
    """Dense retrieval over the 景品表示法 rule KB with article-number metadata."""

    # S-1: read-only retrieval over the public statute KB.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, retriever: Any | None = None, top_k: int = 6, score_threshold: float = 0.75):
        self._retriever = retriever
        self._top_k = top_k
        self._score_threshold = score_threshold

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query_text", "")
        chunks = retrieve_statute(
            query, retriever=self._retriever, top_k=self._top_k, score_threshold=self._score_threshold
        )
        flags = [] if chunks else ["insufficient_grounding"]
        emit_trace_event(
            "statute_retrieved",
            {"correlation_id": state.get("correlation_id"), "n_chunks": len(chunks), "flags": flags},
            state,
        )
        return {"statute_chunks": chunks, "status": AgentStatus.SUCCESS.value}
