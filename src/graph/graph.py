"""AgentCore Platform v1.0 — outer graph for RET-C2-623 (Cat 2).

Outer AgentBaseGraph backbone with the eligibility query workflow encapsulated in a
GraphNode (the `main` slot) wrapping the inner BaseGraph. The GraphNode subclass lives
in this file (not src/nodes/) so the PB-6 probe does not mis-assert its delegating lifecycle.
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class EligibilityGraphNode(GraphNode):
    """Wraps the inner eligibility query workflow; assigned to the `main` slot."""

    # S-1: outer main-slot wrapper — a node in the outer backbone receiving caller input,
    # so it carries the same requirement the manifest declares and its pre/post siblings
    # enforce. Left undeclared it inherits ANONYMOUS, and gate-trust-level-check does not
    # scan GraphNode subclasses, so CI would not report the gap.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        retriever: Any | None = None,
        llm: Any | None = None,
        top_k_policy: int = 8,
        top_k_statute: int = 6,
        score_threshold: float = 0.75,
    ):
        super().__init__()
        self._retriever = retriever
        self._llm = llm
        self._top_k_policy = top_k_policy
        self._top_k_statute = top_k_statute
        self._score_threshold = score_threshold

    def get_subgraph(self) -> AgentBaseGraph:
        from src.graph.domain_workflow_graph import DomainWorkflowGraph

        sg = DomainWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit dispatch into the inner workflow.
        # Progress (non-terminal) event for the caller, emitted as the subgraph step
        # begins. Outside the Marketplace runtime this is a no-op emitter.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        emit_trace_event(
            "eligibility_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        value = state.get("validated_input", state.get("user_input", ""))
        return value if isinstance(value, str) else str(value)

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit the workflow outcome.
        emit_trace_event(
            "eligibility_workflow_completed",
            {"correlation_id": state.get("correlation_id"), "verdict": sub_result.get("verdict")},
            state,
        )
        return {
            # Mapped explicitly like every other field — post_process reads it to report
            # a refusal instead of a verdict. The outer marker wins: it names the specific
            # reason, while the inner node can only report the generic one.
            "error_code": state.get("error_code") or sub_result.get("error_code", ""),
            "verdict": sub_result.get("verdict"),
            "rationale": sub_result.get("rationale", ""),
            "policy_citations": sub_result.get("policy_citations", []),
            "statute_citations": sub_result.get("statute_citations", []),
            "disclaimer": sub_result.get("disclaimer", ""),
            "confidence": sub_result.get("confidence", "low"),
            "policy_chunks": sub_result.get("policy_chunks", []),
            "statute_chunks": sub_result.get("statute_chunks", []),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "retriever": self._retriever,
            "llm": self._llm,
            "top_k_policy": self._top_k_policy,
            "top_k_statute": self._top_k_statute,
            "score_threshold": self._score_threshold,
        }


class Graph(AgentBaseGraph):
    """RET-C2-623 outer graph — Summer-sale dynamic-pricing eligibility Q&A (Cat 2)."""

    @property
    def name(self) -> str:
        return "ret-c2-623"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        cfg = self.config if hasattr(self, "config") else {}
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = EligibilityGraphNode(
            retriever=cfg.get("retriever"),
            llm=cfg.get("llm"),
            top_k_policy=cfg.get("top_k_policy", 8),
            top_k_statute=cfg.get("top_k_statute", 6),
            score_threshold=cfg.get("score_threshold", 0.75),
        )
        self._nodes["post_process"] = PostProcessNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
