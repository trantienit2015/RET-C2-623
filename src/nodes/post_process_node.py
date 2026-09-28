"""AgentCore Platform v1.0 — OutputValidate (outer post_process) for RET-C2-623."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.degradation import explain_degradation
from src.services.pricing_qa_service import DISCLAIMER


class PostProcessNode(FunctionNode):
    """OutputValidate — S-3 preservation gate.

    An eligible / not-eligible verdict MUST carry ≥1 policy citation AND ≥1 statute
    citation, and the disclaimer must be present; otherwise the verdict is forced to
    needs-compliance-review (fail-safe). Business enforcement is in execute() (raise-free);
    the _extra_security_gate_output() hook re-checks preservation.
    """

    # S-1: output formatting; standard business trust.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        # A degraded run produced no verdict by design. The output is the reason alone,
        # not the answer shape with blank fields — an empty verdict inside the assessment
        # shape reads as "assessed, nothing found", which is exactly the wrong thing to
        # tell a caller asking whether a promotion is allowed. Every value is a constant,
        # so nothing the refused request left in State reaches the caller. The
        # preservation gate below does not apply: it exists so that no *definitive
        # verdict* leaves without its citations, and a refusal carries no verdict.
        degraded_code = state.get("error_code", "")
        if degraded_code:
            reason = explain_degradation(degraded_code)
            emit_trace_event(
                "answer_degraded",
                {"correlation_id": state.get("correlation_id"), "error_code": degraded_code},
                state,
            )
            return {
                # carried in this node's own dict so the S-3 re-check — which sees that
                # dict, not the full state — can scope itself to produced verdicts
                "error_code": degraded_code,
                "verdict": "",
                "disclaimer": DISCLAIMER,
                "formatted_output": reason,
                "status": AgentStatus.SUCCESS.value,
            }

        verdict = state.get("verdict", "needs-compliance-review")
        policy_cites = state.get("policy_citations", []) or []
        statute_cites = state.get("statute_citations", []) or []
        disclaimer = state.get("disclaimer") or DISCLAIMER

        # Preservation: a definitive verdict must be doubly-grounded + disclaimed.
        if verdict in ("eligible", "not-eligible") and not (policy_cites and statute_cites):
            verdict = "needs-compliance-review"
            emit_trace_event(
                "verdict_downgraded",
                {"correlation_id": state.get("correlation_id"), "reason": "insufficient_citations"},
                state,
            )

        answer = {
            "verdict": verdict,
            "rationale": state.get("rationale", ""),
            "policy_citations": policy_cites,
            "statute_citations": statute_cites,
            "disclaimer": disclaimer,
            "confidence": state.get("confidence", "low"),
        }
        emit_trace_event(
            "answer_validated",
            {"correlation_id": state.get("correlation_id"), "verdict": verdict},
            state,
        )
        return {
            "verdict": verdict,
            "disclaimer": disclaimer,
            "formatted_output": answer,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation: reject an output whose definitive verdict lost its citations
        or disclaimer. Runs after execute(); always returns a dict, never raises.
        """
        # The gate applies to produced verdicts. A degraded run carries a refusal
        # instead — so the check is scoped by the degradation marker, not weakened.
        if state.get("error_code"):
            return state
        fo = state.get("formatted_output")
        if isinstance(fo, dict) and fo.get("verdict") in ("eligible", "not-eligible"):
            if not (fo.get("policy_citations") and fo.get("statute_citations") and fo.get("disclaimer")):
                return {
                    "formatted_output": {
                        **fo,
                        "verdict": "needs-compliance-review",
                        "disclaimer": DISCLAIMER,
                        "note": "downgraded by S-3 preservation gate",
                    },
                    "verdict": "needs-compliance-review",
                    "status": state.get("status"),
                }
        return state
