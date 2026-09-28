"""AgentCore Platform v1.0 — EligibilityAssess (inner, LLM) for RET-C2-623."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.pricing_qa_service import assess_eligibility


class EligibilityAssessNode(FunctionNode):
    """Grounded eligibility determination from both retrieval sets (temperature 0.0)."""

    # S-1: reasoning over retrieved context; standard business trust.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query_text", "")
        policy = state.get("policy_chunks", [])
        statute = state.get("statute_chunks", [])
        result = assess_eligibility(query, policy, statute, llm=self._llm)
        emit_trace_event(
            "eligibility_assessed",
            {"correlation_id": state.get("correlation_id"), "verdict": result["verdict"]},
            state,
        )
        return {
            "verdict": result["verdict"],
            "rationale": result["rationale"],
            "policy_citations": result["policy_citations"],
            "statute_citations": result["statute_citations"],
            "confidence": result["confidence"],
            "status": AgentStatus.SUCCESS.value,
        }
