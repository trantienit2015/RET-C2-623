"""AgentCore Platform v1.0 — deterministic retrieval + eligibility helpers for RET-C2-623.

Pure, side-effect-free helpers used by the inner query workflow: query-facet extraction,
prompt-injection detection, hybrid/dense retrieval (injectable retriever + curated fallback KB),
grounded eligibility determination, and the mandatory compliance disclaimer. No secrets, no I/O,
and no environment-variable access here (secrets are provisioned via InvocationContext upstream).
"""

from __future__ import annotations

import re
from typing import Any

DISCLAIMER = (
    "This is an advisory assessment, not legal advice; the final compliance judgment must be "
    "made by a qualified compliance officer."
)

# Deterministic prompt-injection / KB-dump patterns.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"output\s+the\s+(full|entire)\s+.*(policy|document)", re.I),
    re.compile(r"dump\s+(the\s+)?(kb|knowledge\s*base|policy)", re.I),
]
_CREDENTIAL_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9._-]{20,}"),
]

# Curated fallback KBs (a real deployment injects a tenant vector store).
_POLICY_KB: list[dict[str, Any]] = [
    {
        "id": "POL-SUMMER-01",
        "section": "3.1",
        "text": "Summer sale discounts up to 40% require category-manager sign-off.",
        "keywords": ["summer", "discount", "40", "campaign", "セール"],
    },
    {
        "id": "POL-BUNDLE-02",
        "section": "4.2",
        "text": "Bundle promotions must show the per-item reference price.",
        "keywords": ["bundle", "promotion", "reference price", "セット"],
    },
]
_KEIHIN_KB: list[dict[str, Any]] = [
    {
        "id": "KEIHIN-ART4",
        "article": "第4条",
        "text": "有利誤認表示の禁止 — misleading advantageous representation is prohibited.",
        "keywords": ["discount", "price", "reference", "40", "有利", "セール", "campaign"],
    },
    {
        "id": "KEIHIN-ART5",
        "article": "第5条",
        "text": "景品類の提供制限 — limits on premium offers accompanying sales.",
        "keywords": ["premium", "gift", "景品", "bundle"],
    },
]


def scan_input(text: str) -> list[str]:
    """Return flags for credential/injection patterns (empty = clean)."""
    flags: list[str] = []
    low = text or ""
    if any(p.search(low) for p in _CREDENTIAL_PATTERNS):
        flags.append("credential")
    if _MYNUMBER(low):
        flags.append("my_number")
    if any(p.search(low) for p in _INJECTION_PATTERNS):
        flags.append("prompt_injection")
    return flags


def _MYNUMBER(text: str) -> bool:
    return bool(re.search(r"\d{12}", re.sub(r"\D", "", text or "")))


def extract_facets(query: str) -> dict[str, Any]:
    """Extract retrieval facets (discount level, campaign, product references)."""
    low = (query or "").lower()
    facets: dict[str, Any] = {}
    m = re.search(r"(\d{1,3})\s*%", low)
    if m:
        facets["discount_pct"] = int(m.group(1))
    if "summer" in low or "セール" in query:
        facets["campaign"] = "summer_sale"
    if "bundle" in low or "セット" in query:
        facets["promo_type"] = "bundle"
    return facets


def _keyword_retrieve(kb: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
    low = (query or "").lower()
    scored = []
    for e in kb:
        score = sum(1 for kw in e["keywords"] if kw.lower() in low)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def retrieve_policy(
    query: str, retriever: Any | None = None, top_k: int = 8, score_threshold: float = 0.75
) -> list[dict[str, Any]]:
    """Hybrid retrieval over the internal policy KB (injectable retriever or fallback)."""
    if retriever is not None and hasattr(retriever, "hybrid_search"):
        return list(retriever.hybrid_search(query, k=top_k, score_threshold=score_threshold) or [])[:top_k]
    return _keyword_retrieve(_POLICY_KB, query, top_k)


def retrieve_statute(
    query: str, retriever: Any | None = None, top_k: int = 6, score_threshold: float = 0.75
) -> list[dict[str, Any]]:
    """Dense retrieval over the 景品表示法 rule KB (injectable retriever or fallback)."""
    if retriever is not None and hasattr(retriever, "dense_search"):
        return list(retriever.dense_search(query, k=top_k, score_threshold=score_threshold) or [])[:top_k]
    return _keyword_retrieve(_KEIHIN_KB, query, top_k)


def assess_eligibility(
    query: str, policy_chunks: list[dict[str, Any]], statute_chunks: list[dict[str, Any]], llm: Any | None = None
) -> dict[str, Any]:
    """Grounded eligibility determination from both retrieval sets.

    Fail-safe: insufficient grounding (missing either side) → needs-compliance-review, never guess.
    An injected LLM may refine the rationale; the verdict logic stays deterministic and grounded.
    """
    policy_citations = [c.get("section") for c in policy_chunks if c.get("section")]
    statute_citations = [c.get("article") for c in statute_chunks if c.get("article")]

    if not policy_chunks or not statute_chunks:
        return {
            "verdict": "needs-compliance-review",
            "rationale": "Insufficient grounding: missing policy or statute context.",
            "policy_citations": policy_citations,
            "statute_citations": statute_citations,
            "confidence": "low",
        }

    rationale = (
        f"Grounded in policy {policy_citations} and 景品表示法 {statute_citations}. "
        f"The requested pricing action is permitted subject to the cited policy conditions "
        f"and misleading-representation limits."
    )
    if llm is not None and hasattr(llm, "complete"):
        try:
            refined = llm.complete([{"role": "user", "content": rationale + f"\nQuery: {query}"}])
            if isinstance(refined, str) and refined.strip():
                rationale = refined.strip()
        except Exception:  # noqa: BLE001 - LLM refinement is best-effort; deterministic rationale stands
            pass

    # Deterministic guardrail: aggressive discount above policy sign-off threshold → review.
    facets = extract_facets(query)
    verdict = "eligible"
    if facets.get("discount_pct", 0) > 40:
        verdict = "needs-compliance-review"
        rationale += " Discount exceeds the 40% policy sign-off threshold — escalate to compliance."

    return {
        "verdict": verdict,
        "rationale": rationale,
        "policy_citations": policy_citations,
        "statute_citations": statute_citations,
        "confidence": "high" if verdict == "eligible" else "medium",
    }
