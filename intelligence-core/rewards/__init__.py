"""
SSIP Intelligence Core - Rewards Module
Credit card rewards schema and optimization.
"""

from .schema import (
    RewardType,
    BonusCategory,
    RewardRate,
    CreditCard,
    CardWallet,
    # Pre-built cards
    create_chase_sapphire_preferred,
    create_amex_gold,
    create_citi_double_cash,
    create_chase_freedom_flex,
    create_discover_it,
    create_amazon_prime_visa,
    create_default_wallet,
)

__all__ = [
    "RewardType",
    "BonusCategory",
    "RewardRate",
    "CreditCard",
    "CardWallet",
    "create_chase_sapphire_preferred",
    "create_amex_gold",
    "create_citi_double_cash",
    "create_chase_freedom_flex",
    "create_discover_it",
    "create_amazon_prime_visa",
    "create_default_wallet",
]
