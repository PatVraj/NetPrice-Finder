"""
Retailer Intelligence Module for SSIP
Provides persistent caching and intelligent decision-making for cashback and promo codes.
"""

from .intelligence import RetailerIntelligence
from .models import (
    RetailerDeals,
    SavingsStrategy,
    StrategyOption,
    PaymentBonus,
    RetailerTier,
)
from .database import RetailerDatabase
from .cache import RetailerCache

__all__ = [
    "RetailerIntelligence",
    "RetailerDeals",
    "SavingsStrategy",
    "StrategyOption",
    "PaymentBonus",
    "RetailerTier",
    "RetailerDatabase",
    "RetailerCache",
]
