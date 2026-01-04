"""
SSIP Intelligence Core - Optimizer Module
Net price optimization across retailers, cashback, and rewards.
"""

from .net_price import (
    PaymentMethod,
    ProductInfo,
    CouponResult,
    SavingsBreakdown,
    RetailerOption,
    OptimizationResult,
    NetPriceOptimizer,
    ProductScraper,
    CouponFinder,
    # Convenience functions
    find_best_price,
    compare_retailers,
    calculate_net_price,
    # Utilities
    detect_retailer,
    extract_domain,
    KNOWN_RETAILERS,
)

__all__ = [
    "PaymentMethod",
    "ProductInfo",
    "CouponResult",
    "SavingsBreakdown",
    "RetailerOption",
    "OptimizationResult",
    "NetPriceOptimizer",
    "ProductScraper",
    "CouponFinder",
    "find_best_price",
    "compare_retailers",
    "calculate_net_price",
    "detect_retailer",
    "extract_domain",
    "KNOWN_RETAILERS",
]
