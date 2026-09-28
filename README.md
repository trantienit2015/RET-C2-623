# RET-C2-623 — RetailSummerSaleDynamicPricingQAAgent

> **Category**: Cat 2 (multi-step workflow for a specific job-to-be-done)
> **Industry**: RET

## Overview

This agent answers store-manager questions about campaign and pricing eligibility. It grounds each answer in two knowledge bases at once — the retailer's own policy and the applicable advertising-and-premiums rules — and returns a verdict of eligible, not eligible, or needs compliance review, with citations to the policy section and the statutory article behind it. It is read-only and advisory: it never writes back to a pricing system.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Credentials — optional, you supply them

This agent can use an Azure OpenAI deployment to refine the wording of its rationale. The
deployment's credentials are **not** in this repository and are not shipped with it: they
are yours and they bill to your account. They are optional, so `config/agent.yaml` does
not declare them as startup requirements:

| Name | Used for |
|---|---|
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` | Reasoning over the retrieved policy and statute text |

Set them as environment variables on the process that runs the agent. Never commit them,
and never put them in `config/config.yaml` — that file ships in the image.

**The model is optional.** It refines the wording of the rationale. If it cannot be
reached, the deterministic verdict and rationale stand unchanged.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
