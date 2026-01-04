"""
Data models for Retailer Intelligence System.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class RetailerTier(Enum):
    """Retailer importance tier for refresh prioritization."""
    MAJOR = "major"       # 4-hour TTL, background refresh
    STANDARD = "standard" # 12-hour TTL, on-demand refresh
    MINOR = "minor"       # 24-hour TTL, on-demand only


class DiscountType(Enum):
    """Type of discount for promo codes."""
    PERCENT = "percent"       # 20% off
    FIXED = "fixed"           # $10 off
    BOGO = "bogo"            # Buy one get one
    FREE_SHIPPING = "shipping" # Free shipping
    GIFT = "gift"            # Free gift with purchase


class PaymentMethodType(Enum):
    """Payment methods that may have bonuses."""
    PAYPAL = "paypal"
    VENMO = "venmo"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    AMAZON_PAY = "amazon_pay"
    KLARNA = "klarna"
    AFTERPAY = "afterpay"


# =============================================================================
# Database Models
# =============================================================================

@dataclass
class Retailer:
    """A retailer in the database."""
    id: Optional[int] = None
    name: str = ""
    normalized_name: str = ""  # lowercase, no spaces
    domain: Optional[str] = None
    category: Optional[str] = None
    mcc_code: Optional[str] = None  # For CC rewards
    tier: RetailerTier = RetailerTier.STANDARD
    created_at: Optional[datetime] = None
    last_scraped_at: Optional[datetime] = None
    
    def __post_init__(self):
        if not self.normalized_name and self.name:
            self.normalized_name = self.name.lower().strip().replace(" ", "")
        if isinstance(self.tier, str):
            self.tier = RetailerTier(self.tier)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "domain": self.domain,
            "category": self.category,
            "mcc_code": self.mcc_code,
            "tier": self.tier.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_scraped_at": self.last_scraped_at.isoformat() if self.last_scraped_at else None,
        }
    
    @classmethod
    def from_row(cls, row: tuple, columns: list[str]) -> "Retailer":
        """Create from database row."""
        data = dict(zip(columns, row))
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            normalized_name=data.get("normalized_name", ""),
            domain=data.get("domain"),
            category=data.get("category"),
            mcc_code=data.get("mcc_code"),
            tier=RetailerTier(data.get("tier", "standard")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            last_scraped_at=datetime.fromisoformat(data["last_scraped_at"]) if data.get("last_scraped_at") else None,
        )


@dataclass
class StoredCashbackOffer:
    """A cashback offer stored in the database."""
    id: Optional[int] = None
    retailer_id: int = 0
    platform: str = ""
    
    # Rate info
    cashback_percent: Optional[float] = None
    cashback_fixed: Optional[float] = None
    cashback_text: str = ""
    
    # Metadata
    category: Optional[str] = None
    is_elevated: bool = False
    terms: Optional[str] = None
    affiliate_url: Optional[str] = None
    confidence: float = 1.0
    
    # Timestamps
    expires_at: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    
    @property
    def effective_rate(self) -> float:
        """Get effective rate for comparison."""
        if self.cashback_percent:
            return self.cashback_percent
        if self.cashback_fixed:
            return self.cashback_fixed  # Treat as equivalent to percentage
        return 0.0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "retailer_id": self.retailer_id,
            "platform": self.platform,
            "cashback_percent": self.cashback_percent,
            "cashback_fixed": self.cashback_fixed,
            "cashback_text": self.cashback_text,
            "category": self.category,
            "is_elevated": self.is_elevated,
            "terms": self.terms,
            "affiliate_url": self.affiliate_url,
            "confidence": self.confidence,
            "effective_rate": self.effective_rate,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
    
    @classmethod
    def from_row(cls, row: tuple, columns: list[str]) -> "StoredCashbackOffer":
        """Create from database row."""
        data = dict(zip(columns, row))
        return cls(
            id=data.get("id"),
            retailer_id=data.get("retailer_id", 0),
            platform=data.get("platform", ""),
            cashback_percent=data.get("cashback_percent"),
            cashback_fixed=data.get("cashback_fixed"),
            cashback_text=data.get("cashback_text", ""),
            category=data.get("category"),
            is_elevated=bool(data.get("is_elevated", False)),
            terms=data.get("terms"),
            affiliate_url=data.get("affiliate_url"),
            confidence=data.get("confidence", 1.0),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            scraped_at=datetime.fromisoformat(data["scraped_at"]) if data.get("scraped_at") else None,
        )


@dataclass
class StoredPromoCode:
    """A promo code stored in the database."""
    id: Optional[int] = None
    retailer_id: int = 0
    source: str = ""
    
    # Code and description
    code: str = ""
    description: str = ""
    
    # Discount breakdown
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[float] = None
    minimum_purchase: Optional[float] = None
    maximum_discount: Optional[float] = None
    
    # Validity
    verified: bool = False
    success_rate: Optional[float] = None
    
    # Tracking
    times_used: int = 0
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    
    @property
    def effective_value(self) -> float:
        """Estimated value for comparison (assume $100 purchase)."""
        if self.discount_type == DiscountType.PERCENT and self.discount_value:
            return self.discount_value
        if self.discount_type == DiscountType.FIXED and self.discount_value:
            return self.discount_value
        return 0.0
    
    def calculate_discount(self, purchase_amount: float) -> float:
        """Calculate actual discount for a purchase amount."""
        if not self.discount_value:
            return 0.0
        
        # Check minimum purchase requirement
        if self.minimum_purchase and purchase_amount < self.minimum_purchase:
            return 0.0
        
        if self.discount_type == DiscountType.PERCENT:
            discount = purchase_amount * (self.discount_value / 100)
        elif self.discount_type == DiscountType.FIXED:
            discount = self.discount_value
        else:
            discount = 0.0
        
        # Apply maximum discount cap
        if self.maximum_discount:
            discount = min(discount, self.maximum_discount)
        
        return discount
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "retailer_id": self.retailer_id,
            "source": self.source,
            "code": self.code,
            "description": self.description,
            "discount_type": self.discount_type.value if self.discount_type else None,
            "discount_value": self.discount_value,
            "minimum_purchase": self.minimum_purchase,
            "maximum_discount": self.maximum_discount,
            "verified": self.verified,
            "success_rate": self.success_rate,
            "times_used": self.times_used,
            "effective_value": self.effective_value,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
    
    @classmethod
    def from_row(cls, row: tuple, columns: list[str]) -> "StoredPromoCode":
        """Create from database row."""
        data = dict(zip(columns, row))
        discount_type = None
        if data.get("discount_type"):
            try:
                discount_type = DiscountType(data["discount_type"])
            except ValueError:
                pass
        
        return cls(
            id=data.get("id"),
            retailer_id=data.get("retailer_id", 0),
            source=data.get("source", ""),
            code=data.get("code", ""),
            description=data.get("description", ""),
            discount_type=discount_type,
            discount_value=data.get("discount_value"),
            minimum_purchase=data.get("minimum_purchase"),
            maximum_discount=data.get("maximum_discount"),
            verified=bool(data.get("verified", False)),
            success_rate=data.get("success_rate"),
            times_used=data.get("times_used", 0),
            last_used_at=datetime.fromisoformat(data["last_used_at"]) if data.get("last_used_at") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            scraped_at=datetime.fromisoformat(data["scraped_at"]) if data.get("scraped_at") else None,
        )


@dataclass
class PaymentBonus:
    """A payment method bonus for a retailer."""
    id: Optional[int] = None
    retailer_id: int = 0
    method: PaymentMethodType = PaymentMethodType.PAYPAL
    
    # Bonus details
    bonus_type: str = "cashback"  # cashback, points, discount
    bonus_value: float = 0.0
    bonus_text: str = ""
    
    # Validity
    terms: Optional[str] = None
    expires_at: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "retailer_id": self.retailer_id,
            "method": self.method.value if isinstance(self.method, PaymentMethodType) else self.method,
            "bonus_type": self.bonus_type,
            "bonus_value": self.bonus_value,
            "bonus_text": self.bonus_text,
            "terms": self.terms,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


# =============================================================================
# Aggregated Response Models
# =============================================================================

@dataclass
class RetailerDeals:
    """Complete deal information for a retailer."""
    retailer: str
    retailer_id: int
    tier: RetailerTier
    
    # All offers (not just best)
    cashback_offers: list[StoredCashbackOffer] = field(default_factory=list)
    promo_codes: list[StoredPromoCode] = field(default_factory=list)
    payment_bonuses: list[PaymentBonus] = field(default_factory=list)
    
    # Quick access to best options
    best_cashback: Optional[StoredCashbackOffer] = None
    best_promo: Optional[StoredPromoCode] = None
    
    # Metadata
    cached_at: Optional[datetime] = None
    is_fresh: bool = True
    data_sources: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        self._update_best()
    
    def _update_best(self):
        """Update best cashback and promo based on effective values."""
        if self.cashback_offers:
            self.best_cashback = max(
                self.cashback_offers, 
                key=lambda o: o.effective_rate
            )
        if self.promo_codes:
            self.best_promo = max(
                self.promo_codes,
                key=lambda p: p.effective_value
            )
    
    def to_dict(self) -> dict:
        return {
            "retailer": self.retailer,
            "retailer_id": self.retailer_id,
            "tier": self.tier.value,
            "cashback_offers": [o.to_dict() for o in self.cashback_offers],
            "promo_codes": [p.to_dict() for p in self.promo_codes],
            "payment_bonuses": [b.to_dict() for b in self.payment_bonuses],
            "best_cashback": self.best_cashback.to_dict() if self.best_cashback else None,
            "best_promo": self.best_promo.to_dict() if self.best_promo else None,
            "cached_at": self.cached_at.isoformat() if self.cached_at else None,
            "is_fresh": self.is_fresh,
            "data_sources": self.data_sources,
            "total_offers": len(self.cashback_offers),
            "total_promos": len(self.promo_codes),
        }


@dataclass
class StrategyOption:
    """A single savings strategy option."""
    name: str  # e.g., "Rakuten + Chase Freedom"
    
    # Cashback
    cashback_platform: Optional[str] = None
    cashback_percent: float = 0.0
    cashback_amount: float = 0.0
    
    # Promo code
    promo_code: Optional[str] = None
    promo_description: Optional[str] = None
    promo_discount: float = 0.0
    
    # Credit card
    credit_card: Optional[str] = None
    cc_reward_percent: float = 0.0
    cc_reward_amount: float = 0.0
    
    # Payment method
    payment_method: Optional[str] = None
    payment_bonus_percent: float = 0.0
    payment_bonus_amount: float = 0.0
    
    # Net effect
    total_savings_percent: float = 0.0
    total_savings_amount: float = 0.0
    net_price: float = 0.0
    
    # Stackability info
    is_stackable: bool = True
    conflicts: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SavingsStrategy:
    """Optimal savings strategy for a purchase."""
    retailer: str
    purchase_amount: float
    
    # Recommended approach
    recommended_strategy: Optional[StrategyOption] = None
    
    # All options ranked by effective savings
    all_strategies: list[StrategyOption] = field(default_factory=list)
    
    # Summary totals
    max_cashback_percent: float = 0.0
    max_promo_value: float = 0.0
    max_cc_rewards_percent: float = 0.0
    estimated_total_savings: float = 0.0
    estimated_net_price: float = 0.0
    
    # Explanation
    steps: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.all_strategies and not self.recommended_strategy:
            self.recommended_strategy = self.all_strategies[0]
    
    def to_dict(self) -> dict:
        return {
            "retailer": self.retailer,
            "purchase_amount": self.purchase_amount,
            "recommended_strategy": self.recommended_strategy.to_dict() if self.recommended_strategy else None,
            "all_strategies": [s.to_dict() for s in self.all_strategies],
            "max_cashback_percent": self.max_cashback_percent,
            "max_promo_value": self.max_promo_value,
            "max_cc_rewards_percent": self.max_cc_rewards_percent,
            "estimated_total_savings": self.estimated_total_savings,
            "estimated_net_price": self.estimated_net_price,
            "steps": self.steps,
        }


# =============================================================================
# Major Retailers List
# =============================================================================

MAJOR_RETAILERS = [
    # General/Big Box
    "amazon", "walmart", "target", "costco", "samsclub",
    
    # Electronics
    "bestbuy", "newegg", "bhphoto", "apple", "samsung", "dell", "hp", "lenovo",
    
    # Department Stores
    "macys", "nordstrom", "kohls", "jcpenney", "dillards", "bloomingdales",
    
    # Fashion
    "nike", "adidas", "underarmour", "gap", "oldnavy", "bananarepublic",
    "hm", "zara", "forever21", "asos", "shein",
    
    # Beauty
    "sephora", "ulta", "bluemercury", "dermstore",
    
    # Home
    "homedepot", "lowes", "wayfair", "overstock", "bedbathandbeyond",
    "williams-sonoma", "potterybarn", "crateandbarrel", "ikea",
    
    # Grocery
    "instacart", "shipt", "freshdirect", "peapod",
    
    # Travel
    "expedia", "hotels", "booking", "airbnb", "vrbo", "priceline",
    "southwest", "delta", "united", "aa",
    
    # Jewelry
    "pandora", "tiffany", "kay", "zales", "jared", "bluenile",
    
    # Sports/Outdoor
    "dickssportinggoods", "rei", "backcountry", "cabelas", "basspro",
    
    # Pets
    "petco", "petsmart", "chewy",
    
    # Office
    "staples", "officedepot",
    
    # Other
    "ebay", "etsy", "wish", "aliexpress",
]


def normalize_retailer_name(name: str) -> str:
    """Normalize retailer name for consistent lookups."""
    return name.lower().strip().replace(" ", "").replace("-", "").replace("'", "")


def is_major_retailer(name: str) -> bool:
    """Check if a retailer is considered 'major'."""
    normalized = normalize_retailer_name(name)
    return normalized in MAJOR_RETAILERS
