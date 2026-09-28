"""AgentCore Platform v1.0 — inner query workflow graph for RET-C2-623."""

from typing import Any

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from langgraph.graph import END, START

from src.nodes.disclaimer_annotate_node import DisclaimerAnnotateNode
from src.nodes.eligibility_assess_node import EligibilityAssessNode
from src.nodes.keihin_rule_retrieve_node import KeihinRuleRetrieveNode
from src.nodes.policy_kb_retrieve_node import PolicyKBRetrieveNode
from src.schemas.state import State


class DomainWorkflowGraph(BaseGraph):
    """Inner multi-step eligibility query workflow (Cat 2).

    START → policy_kb_retrieve → keihin_rule_retrieve → eligibility_assess
          → disclaimer_annotate → END
    """

    @property
    def name(self) -> str:
        return "ret_c2_623_eligibility_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        retriever = self.config.get("retriever") if hasattr(self, "config") else None
        top_k_policy = self.config.get("top_k_policy", 8) if hasattr(self, "config") else 8
        top_k_statute = self.config.get("top_k_statute", 6) if hasattr(self, "config") else 6
        threshold = self.config.get("score_threshold", 0.75) if hasattr(self, "config") else 0.75
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["policy_kb_retrieve"] = PolicyKBRetrieveNode(
            retriever=retriever, top_k=top_k_policy, score_threshold=threshold
        )
        self._nodes["keihin_rule_retrieve"] = KeihinRuleRetrieveNode(
            retriever=retriever, top_k=top_k_statute, score_threshold=threshold
        )
        self._nodes["eligibility_assess"] = EligibilityAssessNode(llm=llm)
        self._nodes["disclaimer_annotate"] = DisclaimerAnnotateNode()

    def add_edges(self) -> None:
        # Conditional after the first retrieval step: a refused request must not reach the
        # statute lookup or the assessment. An unconditional edge would run the rest of
        # the pipeline on a request the first node already declined.
        self._sg.add_edge(START, "policy_kb_retrieve")
        self._sg.add_conditional_edges(
            "policy_kb_retrieve",
            lambda s: END if self._is_error(s) else "keihin_rule_retrieve",
            {"keihin_rule_retrieve": "keihin_rule_retrieve", END: END},
        )
        self._sg.add_edge("keihin_rule_retrieve", "eligibility_assess")
        self._sg.add_edge("eligibility_assess", "disclaimer_annotate")
        self._sg.add_edge("disclaimer_annotate", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        # A degraded rejection ends the run as SUCCESS, so keying only on the status
        # would let the remaining nodes run on a request that was already refused.
        return bool(state.get("error_code")) or state.get("status") == AgentStatus.ERROR.value

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "disclaimer_annotate"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "error_code": state.get("error_code"),
            "verdict": state.get("verdict"),
            "rationale": state.get("rationale", ""),
            "policy_citations": state.get("policy_citations", []),
            "statute_citations": state.get("statute_citations", []),
            "disclaimer": state.get("disclaimer", ""),
            "confidence": state.get("confidence", "low"),
            "policy_chunks": state.get("policy_chunks", []),
            "statute_chunks": state.get("statute_chunks", []),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
