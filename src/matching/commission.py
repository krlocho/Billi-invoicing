"""Channel commission calculation — fully configurable per tenant.

Commission rates are NEVER hardcoded. They depend on:
- Channel (Booking, Airbnb, Expedia, etc.)
- Program/plan (Genius, Preferred Partner, Visibility Booster, etc.)
- Contract terms (negotiated per hotel)
- Country/market

The system learns actual rates from historical data (RAG) and
falls back to configurable defaults per tenant.
"""

from decimal import Decimal


# These are REFERENCE ranges only — used when no tenant config exists.
# Real rates are loaded from tenant.settings or channel.commission_config.
COMMISSION_REFERENCE = {
    "booking.com": {
        "range": "15-30%",
        "common_rates": {
            "base": 0.15,
            "genius": 0.17,
            "preferred": 0.20,
            "preferred_plus": 0.22,
            "visibility_booster": 0.25,
        },
        "psf": {"range": "0-1.6%", "default": 0.013},
        "notes": "Commission varies by program. PSF (Payments Service Fee) applies when Booking handles payments.",
    },
    "airbnb": {
        "range": "3-16%",
        "common_rates": {
            "host_only": 0.14,       # Host-only fee model (most common)
            "split_fee": 0.03,       # Split fee model (host pays less, guest pays more)
            "simplified": 0.15,      # Simplified pricing
        },
        "notes": "Depends on fee model chosen by host. Host-only ~14-16%, Split ~3%.",
    },
    "expedia": {
        "range": "15-25%",
        "common_rates": {
            "base": 0.18,
            "collect": 0.22,
            "merchant": 0.25,
        },
        "notes": "Varies by contract and collect/merchant model.",
    },
    "stripe": {
        "range": "1.4-2.9% + fixed",
        "common_rates": {
            "european": 0.014,       # 1.4% + €0.25 for European cards
            "non_european": 0.029,   # 2.9% + €0.25 for non-European cards
        },
        "notes": "Processing fee only — no channel commission (own website).",
    },
    "sunweb": {
        "range": "15-25%",
        "common_rates": {"base": 0.20},
        "notes": "Tour operator — varies by contract.",
    },
}


def get_commission_rate(
    channel_code: str,
    rate_type: str = "base",
    tenant_config: dict | None = None,
) -> float:
    """Get commission rate for a channel.

    Priority:
    1. tenant_config (from channel.commission_config in DB) — most accurate
    2. Reference defaults — fallback only
    """
    # 1. Try tenant-specific config first
    if tenant_config:
        # Tenant config can have direct rate or rate_type mapping
        if isinstance(tenant_config, dict):
            if rate_type in tenant_config:
                return float(tenant_config[rate_type])
            if "base_rate" in tenant_config:
                return float(tenant_config["base_rate"])
            if "base" in tenant_config:
                return float(tenant_config["base"])

    # 2. Fallback to reference
    channel_ref = COMMISSION_REFERENCE.get(channel_code.lower(), {})
    common = channel_ref.get("common_rates", {})
    if rate_type in common:
        return common[rate_type]
    if "base" in common:
        return common["base"]

    return 0.15  # Safe fallback


def get_psf_rate(channel_code: str, tenant_config: dict | None = None) -> float:
    """Get Payments Service Fee rate (mainly Booking.com)."""
    if tenant_config and "psf_rate" in tenant_config:
        return float(tenant_config["psf_rate"])
    if tenant_config and "psf" in tenant_config:
        return float(tenant_config["psf"])

    channel_ref = COMMISSION_REFERENCE.get(channel_code.lower(), {})
    psf_info = channel_ref.get("psf", {})
    return psf_info.get("default", 0.0)


def calculate_expected_net(
    gross_amount: float,
    channel_code: str,
    tenant_config: dict | None = None,
) -> float:
    """Calculate expected net payment after channel commission.

    For Booking: net = gross * (1 - commission%) - gross * PSF%
    For Stripe:  net = gross - (gross * processing_fee + ~€0.25 per txn)
    For others:  net = gross * (1 - commission%)
    """
    commission = get_commission_rate(channel_code, tenant_config=tenant_config)
    psf = get_psf_rate(channel_code, tenant_config=tenant_config)

    net = gross_amount * (1 - commission)
    if psf > 0:
        net -= gross_amount * psf
    return net


def calculate_expected_net_for_group(
    gross_amounts: list[float],
    channel_code: str,
    tenant_config: dict | None = None,
) -> float:
    """Calculate expected net for a group of reservations."""
    total_gross = sum(gross_amounts)
    return calculate_expected_net(total_gross, channel_code, tenant_config)


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


def get_tax_config(tenant_settings: dict | None = None) -> dict:
    """Get tax configuration for a tenant.

    Returns dict with tax_type, tax_rate, tax_name.
    Supports: IGIC (Canarias), IVA (Spain), VAT (EU), etc.
    """
    if tenant_settings:
        return {
            "tax_type": tenant_settings.get("tax_type", "IVA"),
            "tax_rate": float(tenant_settings.get("tax_rate", 10.0)),
            "tax_name": tenant_settings.get("tax_name", "IVA"),
        }

    # Default — IVA 10% (Spain mainland hotels)
    return {"tax_type": "IVA", "tax_rate": 10.0, "tax_name": "IVA"}
