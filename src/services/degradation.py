"""Caller-facing wording for runs that end without an assessment.

Each outcome here is reported by completing the run with an allow-listed ``error_code``
and a fixed sentence derived from that code alone. No request value is ever
interpolated, so a notice can never echo caller content back. On such a run
``status=SUCCESS`` means the agent finished handling the request safely; it does not
mean an assessment was returned.

Caller-correctable: EMPTY_INPUT, a request with no question in it. The sentence names
what to send instead.

Policy withholding on input: REQUEST_NOT_ACCEPTED. A personal-number identifier that
reaches this agent unmasked is not accepted under its input policy; nothing in the
request is assessed. The framework's own S-2 scan masks the usual forms before the agent
reads the request, and such a question is answered with the number masked.

A definitive verdict that lost its policy or statute citations is not withheld at all —
it is downgraded to needs-compliance-review, which is the fail-safe answer and reaches
the caller intact.

Not reported here, and ending as ``status=ERROR`` instead: credential-shaped content or
an instruction addressed to the agent, which fails closed with no output and no status
conversion; an internally inconsistent run (state a preceding step guarantees is
absent), which is a defect; and a failed call to a required external dependency. None of
these is ever represented as a successful completion. A missing or unusable
configuration is refused at startup rather than reported per request.
"""

from __future__ import annotations

EMPTY_INPUT = "EMPTY_INPUT"
REQUEST_NOT_ACCEPTED = "REQUEST_NOT_ACCEPTED"

_MESSAGES: dict[str, str] = {
    EMPTY_INPUT: (
        "No question was received. Describe the pricing or promotion question to "
        "assess — the campaign, discount or giveaway whose eligibility you need "
        "checked."
    ),
    REQUEST_NOT_ACCEPTED: (
        "The request was not accepted, and nothing in it was assessed. Send the "
        "pricing or promotion question without personal identification numbers."
    ),
}

_FALLBACK = "The request could not be accepted and no assessment was produced."


def explain_degradation(code: str) -> str:
    """Return one caller-facing sentence for a degradation code."""
    return _MESSAGES.get(code, f"{_FALLBACK} [{code}]" if code else _FALLBACK)
