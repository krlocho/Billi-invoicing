"""Channel commission rates and calculation."""

from decimal import Decimal

# Default commission rates per channel (can be overridden per tenant)
DEFAULT_COMMISSIONS: dict[str, dict[str, float]] = {
    "booking.com": {
        "base_rate": 0.15,
        "genius_rate": 0.17,
        "preferred_rate": 0.18,
    },
    "booking": {
        "base_rate": 0.15,
        "genius_rate": 0.17,
        "preferred_rate": 0.18,
    },
    "expedia": {
        "base_rate": 0.15,
        "collect_rate": 0.20,
        "merchant_rate": 0.25,
    },
    "hotelbeds": {
        "base_rate": 0.20,
    },
    "agoda": {
        "base_rate": 0.18,
    },
    "hotels.com": {
        "base_rate": 0.20,
    },
}


def get_commission_rate(channel_code: str, rate_type: str = "base_rate") -> float:
    channel = DEFAULT_COMMISSIONS.get(channel_code.lower(), {})
    return channel.get(rate_type, channel.get("base_rate", 0.15))


def calculate_expected_net(gross_amount: float, channel_code: str) -> float:
    """Calculate what the hotel should receive after channel commission."""
    rate = get_commission_rate(channel_code)
    return gross_amount * (1 - rate)


def calculate_expected_net_for_group(
    gross_amounts: list[float], channel_code: str
) -> float:
    """Calculate expected net for a group of reservations."""
    total_gross = sum(gross_amounts)
    return calculate_expected_net(total_gross, channel_code)


def amount_matches(
    bank_amount: float,
    expected_net: float,
    tolerance_pct: float = 0.03,
) -> tuple[bool, float]:
    """Check if bank amount matches expected net within tolerance.
    Returns (matches, difference).
    """
    if expected_net == 0:
        return False, abs(bank_amount)

    diff = abs(bank_amount - expected_net)
    pct_diff = diff / abs(expected_net)
    return pct_diff <= tolerance_pct, diff
