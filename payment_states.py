"""
Payment state constants for MEGA FREELANCER.

Only PAYMENT_CONFIRMED counts toward verified earnings.
Opportunities, pending payments, and unknown states must NOT increase earnings.
"""

PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"

ALL_PAYMENT_STATES = {
    PAYMENT_UNKNOWN,
    PAYMENT_PENDING,
    PAYMENT_CONFIRMED,
}


def is_verified_earning(payment_status: str) -> bool:
    """Return True only when payment has been verified on-chain or by platform."""
    return payment_status == PAYMENT_CONFIRMED


def calculate_verified_earnings(records: list) -> float:
    """
    Sum reward amounts from records with PAYMENT_CONFIRMED status only.
    Missing or unconfirmed rewards are excluded.
    """
    total = 0.0
    for record in records:
        if not is_verified_earning(record.get("payment_status", PAYMENT_UNKNOWN)):
            continue
        reward = record.get("reward")
        if reward is None:
            reward = record.get("source_reward")
        if reward is None:
            continue
        try:
            total += float(reward)
        except (ValueError, TypeError):
            continue
    return total


def format_reward_display(reward, currency: str = "USD") -> str:
    """Format reward for display; missing rewards show as Unknown."""
    if reward is None:
        return "Unknown"
    try:
        return f"${float(reward):,.2f} {currency or 'USD'}"
    except (ValueError, TypeError):
        return "Unknown"
