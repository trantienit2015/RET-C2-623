"""AgentCore Platform v1.0 — QueryParse (outer pre_process) for RET-C2-623."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.degradation import EMPTY_INPUT, REQUEST_NOT_ACCEPTED

from src.services.pricing_qa_service import extract_facets, scan_input


class PreProcessNode(FunctionNode):
    """QueryParse — normalize the pricing/eligibility query and build the inner
    JSON payload. S-2 domain scan (credentials / 個人番号 / prompt-injection) via
    _extra_security_gate_input(); clean business queries pass through.
    """

    # S-1: store-manager query; standard business trust.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        if state.get("error_code") == REQUEST_NOT_ACCEPTED:
            return {
                "error_code": REQUEST_NOT_ACCEPTED,
                "status": AgentStatus.SUCCESS.value,
                "error_log": ["S-2: rejected input - not assessed"],
            }

        query = (state.get("user_input", "") or "").strip()
        if not query:
            emit_trace_event(
                "query_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty"},
                state,
            )
            # The caller can act on this, so the run completes and carries the reason.
            return {"error_code": EMPTY_INPUT, "status": AgentStatus.SUCCESS.value}

        facets = extract_facets(query)
        payload = {"query": query, "facets": facets}
        emit_trace_event(
            "query_parsed",
            {"correlation_id": state.get("correlation_id"), "facets": facets},
            state,
        )
        return {
            "query_facets": facets,
            "validated_input": json.dumps(payload, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain scan: credentials / My-Number / prompt-injection are rejected.
        Runs before execute(); always returns a dict, never raises.
        """
        flags = scan_input(state.get("user_input", "") or "")
        if {"credential", "prompt_injection"} & set(flags):
            # Security failure: credential-shaped content or an instruction aimed at the
            # agent fails closed - status=ERROR and no output, with no status
            # conversion. __call__() skips execute(), so nothing is assessed.
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"S-2: rejected input ({sorted(set(flags))})"],
            }
        if flags:
            # Policy withholding: a personal-number identifier alone is not accepted
            # under this agent's input policy. The framework's S-2 scan masks the usual
            # forms before this hook runs, so this is a second line for one that arrives
            # unmasked. Marked rather than failed, so execute()
            # returns a fixed notice before it reads the request and nothing in it is
            # assessed. Which check fired is recorded here, in the audit trail, and
            # never reaches the caller-facing wording.
            emit_trace_event(
                "query_rejected",
                {
                    "correlation_id": state.get("correlation_id"),
                    "reason": "s2_input_scan",
                    "flags": sorted(set(flags)),
                },
                state,
            )
            marked = dict(state)
            marked["error_code"] = REQUEST_NOT_ACCEPTED
            return marked
        return state
