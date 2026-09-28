"""The language model is optional, on the deployment path as well as in the graph.

The Marketplace entry point injects a client that resolves the three connection values on
each call, whenever the provider client exists. These tests reproduce a deployment that
supplies none of them: the call is attempted, cannot resolve its values, and the run still
completes on the deterministic verdict and rationale. They also pin the manifest, which
must not turn the optional model into a startup prerequisite.
"""

from pathlib import Path

import yaml

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.base import NullProvider
from framework.secrets.context import bound_secrets

from src.graph.graph import Graph
from src.services.azure_llm import LazyAzureOpenAILLM, REQUIRED_SECRET_KEYS

_ROOT = Path(__file__).resolve().parents[2]
_QUESTION = "Can we run a 30% summer sale discount campaign with reference prices?"


class _CountingLazyLLM(LazyAzureOpenAILLM):
    """The client the entry point injects, counting the calls that reach it."""

    calls = 0

    def complete(self, messages):
        type(self).calls += 1
        return super().complete(messages)


def _invoke(llm):
    config = yaml.safe_load((_ROOT / "config" / "config.yaml").read_text()) or {}
    if llm is not None:
        config["llm"] = llm
    agent = Graph(config=config)
    agent.compile()
    ctx = InvocationContext(session_id="no-credentials", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="t")
    # A bound provider holding none of the values: what a deployment without them supplies.
    with bound_secrets(NullProvider()):
        return agent.invoke(_QUESTION, ctx=ctx)


def test_deployment_without_credentials_completes_on_the_deterministic_path(monkeypatch):
    for key in REQUIRED_SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    _CountingLazyLLM.calls = 0

    with_client = _invoke(_CountingLazyLLM())
    without_client = _invoke(None)

    # The model was really attempted - the fallback is not reached by never calling it.
    assert _CountingLazyLLM.calls >= 1
    assert with_client["status"] == AgentStatus.SUCCESS.value
    # Same verdict, citations and rationale as a run with no model at all.
    assert with_client["output"] == without_client["output"]
    assert with_client["output"]["verdict"] == "eligible"


def test_manifest_does_not_make_the_optional_model_a_startup_prerequisite():
    manifest = yaml.safe_load((_ROOT / "config" / "agent.yaml").read_text())
    requires = manifest["requires"]
    assert not set(REQUIRED_SECRET_KEYS) & set(requires["secrets"])
    assert "openai" not in requires["extras"]
