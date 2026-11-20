"""Deterministic banking guardrails (Blueprint Workflow B, Node 3).

Pure functions with no I/O so the rules can be unit-tested and so the LLM can
never talk its way into an unauthorized refund.
"""
from dataclasses import dataclass

AUTO_CREDIT_APPROVED = "AUTO_CREDIT_APPROVED"
ESCALATED_TO_OPS = "ESCALATED_TO_OPS"

MAX_AUTO_CREDIT_CENTS = 10_000  # $100
MAX_AUTO_CREDIT_RISK = 0.35


@dataclass(frozen=True)
class GuardrailResult:
    decision: str
    amount_within_limit: bool
    risk_within_limit: bool
    no_prior_disputes: bool

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "checks": {
                "amount_within_limit": self.amount_within_limit,
                "risk_within_limit": self.risk_within_limit,
                "no_prior_disputes": self.no_prior_disputes,
            },
        }


def apply_guardrails(amount_cents: int, risk_score: float, prior_disputes: int) -> GuardrailResult:
    """amount <= $100 AND risk <= 0.35 AND prior_disputes == 0 -> auto credit, else escalate."""
    amount_ok = amount_cents <= MAX_AUTO_CREDIT_CENTS
    risk_ok = risk_score <= MAX_AUTO_CREDIT_RISK
    history_ok = prior_disputes == 0
    decision = AUTO_CREDIT_APPROVED if (amount_ok and risk_ok and history_ok) else ESCALATED_TO_OPS
    return GuardrailResult(decision, amount_ok, risk_ok, history_ok)


def decision_confidence(decision: str, risk_score: float) -> float:
    """Confidence that the decision is right, in [0, 1].

    An approval is confident when risk is low; an escalation is confident when risk is
    high. An escalation forced by a hard rule on a low-risk transaction therefore scores
    low, which tells the human reviewer the call is theirs to make.
    """
    value = (1.0 - risk_score) if decision == AUTO_CREDIT_APPROVED else risk_score
    return round(min(max(value, 0.0), 1.0), 3)
