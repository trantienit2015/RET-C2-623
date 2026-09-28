"""AgentCore Platform v1.0 — DisclaimerAnnotate (inner) for RET-C2-623."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.pricing_qa_service import DISCLAIMER


class DisclaimerAnnotateNode(FunctionNode):
    """Deterministic — append the mandatory compliance disclaimer + escalation pointer."""

    # S-1: deterministic annotation, no privileged operation.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        verdict = state.get("verdict", "needs-compliance-review")
        disclaimer = DISCLAIMER
        if verdict == "needs-compliance-review":
            disclaimer += " Escalate this query to the compliance team for a definitive ruling."
        emit_trace_event(
            "disclaimer_annotated",
            {"correlation_id": state.get("correlation_id"), "verdict": verdict},
            state,
        )
        return {"disclaimer": disclaimer, "status": AgentStatus.SUCCESS.value}
