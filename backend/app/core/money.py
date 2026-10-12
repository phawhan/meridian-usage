"""Money is stored as integer nano-USD (USD x 1e9): exact for both sources (D3).

Claude delivers cents with 6 decimals (1e-8 USD); Gemini delivers USD with up to 6 decimals.
"""

from decimal import ROUND_HALF_EVEN, Decimal

NANO_PER_USD = 10**9


def usd_to_nano(usd: Decimal) -> int:
    return int((usd * NANO_PER_USD).to_integral_value(ROUND_HALF_EVEN))


def cents_to_nano(cents: Decimal) -> int:
    return usd_to_nano(cents / 100)


def nano_to_usd(nano: int) -> float:
    """For API responses only, rounded to 6 decimals; never sum these."""
    return round(nano / NANO_PER_USD, 6)
