"""Unit tests for the deterministic dispute rules (no services needed)."""
import pytest

from services.agent_worker.guardrails import (
    AUTO_CREDIT_APPROVED,
    ESCALATED_TO_OPS,
    apply_guardrails,
    decision_confidence,
)


@pytest.mark.parametrize(
    "amount, risk, prior, expected",
    [
        (10_000, 0.35, 0, AUTO_CREDIT_APPROVED),  # both limits are inclusive
        (5_000, 0.10, 0, AUTO_CREDIT_APPROVED),
        (10_001, 0.10, 0, ESCALATED_TO_OPS),  # one cent over $100
        (5_000, 0.351, 0, ESCALATED_TO_OPS),  # risk just over 0.35
        (5_000, 0.10, 1, ESCALATED_TO_OPS),  # any prior dispute
        (60_000, 0.99, 3, ESCALATED_TO_OPS),
    ],
)
def test_guardrail_matrix(amount, risk, prior, expected):
    assert apply_guardrails(amount, risk, prior).decision == expected


def test_confidence_bounds_and_direction():
    assert decision_confidence(AUTO_CREDIT_APPROVED, 0.1) == 0.9
    assert decision_confidence(ESCALATED_TO_OPS, 0.9) == 0.9
    assert decision_confidence(ESCALATED_TO_OPS, 0.1) == 0.1
    assert 0.0 <= decision_confidence(ESCALATED_TO_OPS, 1.7) <= 1.0
