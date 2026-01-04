"""
SSIP Intelligence Core - Cashback Module
Monitor cashback rates across platforms.
"""

from .monitor import (
    CashbackPlatform,
    CashbackOffer,
    MerchantCashback,
    CashbackMonitor,
    # Convenience functions
    find_cashback,
    compare_cashback,
    get_best_platform,
    # Utilities
    parse_cashback_rate,
    get_known_merchant_info,
    KNOWN_MERCHANTS,
)

__all__ = [
    "CashbackPlatform",
    "CashbackOffer",
    "MerchantCashback",
    "CashbackMonitor",
    "find_cashback",
    "compare_cashback",
    "get_best_platform",
    "parse_cashback_rate",
    "get_known_merchant_info",
    "KNOWN_MERCHANTS",
]
