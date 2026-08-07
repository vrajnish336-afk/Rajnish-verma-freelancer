from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

# Configurable Earning Split
OWNER_SHARE = 70
AGENT_SHARE = 30

def validate_shares() -> None:
    if not (0 <= OWNER_SHARE <= 100):
        raise ValueError(f"OWNER_SHARE must be between 0 and 100. Got: {OWNER_SHARE}")
    if not (0 <= AGENT_SHARE <= 100):
        raise ValueError(f"AGENT_SHARE must be between 0 and 100. Got: {AGENT_SHARE}")
    if OWNER_SHARE + AGENT_SHARE != 100:
        raise ValueError(f"Shares must sum to 100. Got sum: {OWNER_SHARE + AGENT_SHARE}")

# Validate immediately upon import
validate_shares()

def calculate_splits(total_amount: float) -> Dict[str, float]:
    """
    Calculates the exact revenue split using precise monetary arithmetic (Decimal).
    Guarantees that owner_share + agent_share exactly equals total_amount.
    This is purely a reporting function and does not modify any state.
    """
    try:
        # Convert to string to avoid float precision issues before Decimal parsing
        total = Decimal(str(total_amount))
    except Exception:
        total = Decimal('0.0')

    owner_pct = Decimal(str(OWNER_SHARE)) / Decimal('100')
    
    # Calculate owner share rounded to 2 decimal places
    owner_amount = (total * owner_pct).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    # The agent gets the exact remainder to ensure perfect summation
    agent_amount = total - owner_amount
    
    return {
        "owner_share": float(owner_amount),
        "agent_share": float(agent_amount),
        "total": float(total)
    }
