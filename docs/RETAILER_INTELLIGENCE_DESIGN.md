# Retailer Intelligence System Design

## 📋 Executive Summary

This document outlines the architecture for a persistent, intelligent caching system that tracks:
- **Cashback rates** across all platforms (Rakuten, TopCashback, Honey, BeFrugal, Swagbucks, TopCashBack)
- **Promo codes** with full context (discount type, minimum purchase, expiry)
- **Payment method combinations** for optimized savings (PayPal + credit card stacking)

The goal is to create a **quick-access reference database** for major retailers that avoids re-scraping on every request while maintaining data freshness.

---

## 🎯 Requirements

### Functional Requirements

1. **Cashback Tracking**
   - Store ALL offers from all platforms (not just best)
   - Track: platform, rate, rate_type (% or $), affiliate_url, scraped_at, expires
   - Support "elevated" or "boosted" rate flags
   - Track confidence score (API vs scrape)

2. **Promo Code Tracking**
   - Store ALL promo codes with context
   - Track: code, source, description, discount_type, discount_value, min_purchase, expires
   - Track verification status and success rate
   - Track last_used timestamp

3. **Quick Access**
   - Sub-100ms lookup for cached retailers
   - Tiered freshness: major retailers refresh daily, others on-demand
   - Background refresh for stale data

4. **Intelligent Decision Engine**
   - Consider all cashback options (PayPal may stack with CC rewards)
   - Rank by effective value considering user's credit cards
   - Support "what-if" analysis (e.g., "What if I pay with PayPal?")

### Non-Functional Requirements

- **Persistence**: Survive container restarts
- **Performance**: < 100ms cache hit, < 10s full scrape
- **Scalability**: Handle 500+ retailers
- **Freshness**: Configurable TTL per retailer tier

---

## 🏗️ Architecture

### Storage Strategy: Hybrid Redis + SQLite

```
┌──────────────────────────────────────────────────────────────────┐
│                        RetailerIntelligence                       │
│                    (Single Point of Access)                       │
└──────────────────────────────────────────────────────────────────┘
                    │                         │
                    ▼                         ▼
        ┌───────────────────┐     ┌───────────────────────┐
        │      Redis        │     │       SQLite          │
        │   (Hot Cache)     │     │   (Persistent Store)  │
        │                   │     │                       │
        │ - Active lookups  │     │ - retailers table     │
        │ - Session data    │     │ - cashback_offers     │
        │ - Rate limiting   │     │ - promo_codes         │
        │ - TTL management  │     │ - payment_methods     │
        └───────────────────┘     │ - scrape_history      │
                                  └───────────────────────┘
```

**Why Hybrid?**
- **Redis**: Already in stack, perfect for hot cache and TTL management
- **SQLite**: Zero-config persistence, survives restarts, easy backup
- **Not MariaDB**: That's reserved for Firefly III, avoid coupling

### Data Flow

```
User Request: "What's the best deal for Amazon?"
                          │
                          ▼
              ┌───────────────────────┐
              │ RetailerIntelligence  │
              │     .get_deals()      │
              └───────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │ Check Redis   │           │ Check SQLite  │
    │  (< 10ms)     │           │  (< 50ms)     │
    └───────────────┘           └───────────────┘
            │                           │
      Cache Hit?                  Has Data?
       │     │                     │     │
      Yes    No                   Yes    No
       │      │                    │      │
       ▼      └────────────────────┼──────┘
   Return                          │
   Cached    ┌─────────────────────┴───────┐
             │         Fresh Enough?        │
             │   (within TTL for tier)      │
             └─────────────────────┬────────┘
                     │             │
                    Yes           No
                     │             │
                     ▼             ▼
               Return from    ┌──────────────┐
               SQLite +       │ Scrape Fresh │
               Warm Redis     │  (Async BG)  │
                              └──────────────┘
                                     │
                                     ▼
                            ┌──────────────┐
                            │ Update Both  │
                            │ Redis+SQLite │
                            └──────────────┘
```

---

## 📊 Database Schema

### SQLite Tables

```sql
-- Core retailer registry
CREATE TABLE retailers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,  -- lowercase, no spaces
    domain TEXT,                            -- e.g., "amazon.com"
    category TEXT,                          -- e.g., "electronics", "clothing"
    mcc_code TEXT,                          -- Merchant Category Code for CC rewards
    tier TEXT DEFAULT 'standard',           -- 'major', 'standard', 'minor'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped_at TIMESTAMP
);

CREATE INDEX idx_retailers_normalized ON retailers(normalized_name);
CREATE INDEX idx_retailers_domain ON retailers(domain);

-- All cashback offers (not just best)
CREATE TABLE cashback_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_id INTEGER NOT NULL,
    platform TEXT NOT NULL,                 -- 'rakuten', 'topcashback', etc.
    
    -- Rate information
    cashback_percent REAL,                  -- e.g., 5.0 for 5%
    cashback_fixed REAL,                    -- e.g., 10.0 for $10
    cashback_text TEXT,                     -- Original text: "Up to 10%"
    
    -- Metadata
    category TEXT,                          -- Platform category
    is_elevated BOOLEAN DEFAULT FALSE,      -- Boosted/special rate
    terms TEXT,
    affiliate_url TEXT,
    
    -- Tracking
    confidence REAL DEFAULT 1.0,            -- 0.0-1.0
    expires_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (retailer_id) REFERENCES retailers(id)
);

CREATE INDEX idx_cashback_retailer ON cashback_offers(retailer_id);
CREATE INDEX idx_cashback_platform ON cashback_offers(platform);
CREATE INDEX idx_cashback_scraped ON cashback_offers(scraped_at);

-- All promo codes with context
CREATE TABLE promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_id INTEGER NOT NULL,
    source TEXT NOT NULL,                   -- 'rakuten', 'honey', 'retailmenot'
    
    -- Code and description
    code TEXT NOT NULL,
    description TEXT,                       -- Full context: "20% off $75+"
    
    -- Discount breakdown
    discount_type TEXT,                     -- 'percent', 'fixed', 'bogo', 'shipping'
    discount_value REAL,                    -- 20.0 for 20% or $20
    minimum_purchase REAL,                  -- $75 minimum
    maximum_discount REAL,                  -- Cap at $50 off
    
    -- Validity
    verified BOOLEAN DEFAULT FALSE,
    success_rate REAL,                      -- 0.0-1.0
    expires_at TIMESTAMP,
    
    -- Tracking
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (retailer_id) REFERENCES retailers(id)
);

CREATE INDEX idx_promo_retailer ON promo_codes(retailer_id);
CREATE INDEX idx_promo_code ON promo_codes(code);
CREATE INDEX idx_promo_verified ON promo_codes(verified);

-- Payment method bonuses (PayPal, Venmo, etc.)
CREATE TABLE payment_bonuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_id INTEGER NOT NULL,
    method TEXT NOT NULL,                   -- 'paypal', 'venmo', 'applepay'
    
    -- Bonus details
    bonus_type TEXT,                        -- 'cashback', 'points', 'discount'
    bonus_value REAL,                       -- 5.0 for 5%
    bonus_text TEXT,
    
    -- Validity
    terms TEXT,
    expires_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (retailer_id) REFERENCES retailers(id)
);

-- Scrape history for debugging and analytics
CREATE TABLE scrape_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_id INTEGER,
    platform TEXT,
    success BOOLEAN,
    error_message TEXT,
    duration_ms INTEGER,
    offers_found INTEGER DEFAULT 0,
    promos_found INTEGER DEFAULT 0,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (retailer_id) REFERENCES retailers(id)
);
```

### Redis Key Structure

```python
# Hot cache with structured keys
# Pattern: {type}:{retailer_normalized}:{platform}

# Retailer metadata (1 hour TTL)
"retailer:amazon" = {
    "id": 1,
    "name": "Amazon",
    "tier": "major",
    "last_scraped": "2025-01-20T10:30:00Z"
}

# Aggregated deals for quick lookup (TTL based on tier)
"deals:amazon" = {
    "cashback_offers": [...],
    "promo_codes": [...],
    "best_cashback": {...},
    "best_promo": {...},
    "payment_bonuses": [...],
    "cached_at": "2025-01-20T10:30:00Z"
}

# Platform-specific offers (for granular invalidation)
"cashback:amazon:rakuten" = {...}
"cashback:amazon:topcashback" = {...}

# Lock keys for preventing duplicate scrapes
"scrape_lock:amazon" = 1  # 5 minute TTL
```

---

## 🔧 RetailerIntelligence Class Design

### Core Interface

```python
class RetailerIntelligence:
    """
    Unified interface for retailer cashback and promo code intelligence.
    
    Features:
    - Tiered caching (major retailers refresh daily)
    - Persistent storage in SQLite
    - Hot cache in Redis
    - Background refresh for stale data
    - Intelligent decision engine for payment optimization
    """
    
    async def get_deals(
        self,
        retailer: str,
        *,
        include_expired: bool = False,
        force_refresh: bool = False,
    ) -> RetailerDeals:
        """
        Get all deals for a retailer.
        
        Returns cashback offers, promo codes, and payment bonuses
        from cache or fresh scrape.
        """
        
    async def get_best_strategy(
        self,
        retailer: str,
        purchase_amount: float,
        *,
        card_wallet: Optional[CardWallet] = None,
        payment_method: Optional[PaymentMethod] = None,
    ) -> SavingsStrategy:
        """
        Calculate the optimal savings strategy for a purchase.
        
        Considers:
        - All cashback platforms
        - User's credit cards (category bonuses)
        - Payment method bonuses (PayPal, etc.)
        - Available promo codes
        """
        
    async def refresh_retailer(
        self,
        retailer: str,
        *,
        platforms: Optional[list[str]] = None,
    ) -> RefreshResult:
        """Force refresh data for a retailer."""
        
    async def get_stale_retailers(
        self,
        max_age_hours: int = 24,
    ) -> list[str]:
        """Get list of retailers needing refresh."""
        
    async def register_major_retailer(
        self,
        name: str,
        domain: str,
        category: Optional[str] = None,
    ) -> None:
        """Register a retailer as 'major' for priority refreshes."""
```

### Data Classes

```python
@dataclass
class RetailerDeals:
    """Complete deal information for a retailer."""
    retailer: str
    retailer_id: int
    tier: str  # 'major', 'standard', 'minor'
    
    # All offers (not just best)
    cashback_offers: list[CashbackOffer]
    promo_codes: list[PromoCode]
    payment_bonuses: list[PaymentBonus]
    
    # Quick access to best options
    best_cashback: Optional[CashbackOffer]
    best_promo: Optional[PromoCode]
    
    # Metadata
    cached_at: datetime
    is_fresh: bool
    data_sources: list[str]  # Platforms that provided data


@dataclass
class SavingsStrategy:
    """Optimal savings strategy for a purchase."""
    retailer: str
    purchase_amount: float
    
    # Recommended approach
    recommended_cashback: Optional[CashbackOffer]
    recommended_promo: Optional[PromoCode]
    recommended_card: Optional[str]
    recommended_payment: Optional[str]
    
    # All options ranked by effective savings
    all_strategies: list[StrategyOption]
    
    # Totals
    max_cashback_percent: float
    max_promo_value: float
    max_cc_rewards: float
    estimated_total_savings: float
    
    # Explanation
    steps: list[str]


@dataclass
class StrategyOption:
    """A single savings strategy option."""
    name: str  # e.g., "Rakuten + Chase Freedom"
    
    cashback_platform: Optional[str]
    cashback_percent: float
    
    promo_code: Optional[str]
    promo_value: float
    
    credit_card: Optional[str]
    cc_reward_percent: float
    
    payment_method: Optional[str]
    payment_bonus: float
    
    # Net effect
    total_savings_percent: float
    total_savings_amount: float
    
    # Stackability (can these be combined?)
    stackable: bool
    conflicts: list[str]
```

---

## ⏰ Tier-Based Refresh Strategy

### Retailer Tiers

| Tier | Examples | Default TTL | Background Refresh |
|------|----------|-------------|-------------------|
| **Major** | Amazon, Target, Walmart, Best Buy, Macy's | 4 hours | Yes, every 4h |
| **Standard** | Mid-tier retailers | 12 hours | On-demand |
| **Minor** | Small/rare retailers | 24 hours | On-demand only |

### TTL Configuration

```python
TIER_TTL = {
    "major": timedelta(hours=4),
    "standard": timedelta(hours=12),
    "minor": timedelta(hours=24),
}

MAJOR_RETAILERS = [
    "amazon", "target", "walmart", "bestbuy", "macys",
    "nordstrom", "kohls", "sephora", "ulta", "nike",
    "adidas", "apple", "samsung", "dell", "hp",
    "homedepot", "lowes", "wayfair", "overstock",
    "ebay", "newegg", "costco", "samsclub",
]
```

### Background Refresh Worker

```python
async def background_refresh_worker():
    """
    Background task that refreshes stale major retailers.
    Runs every 30 minutes, refreshes up to 5 retailers per cycle.
    """
    while True:
        stale = await intelligence.get_stale_retailers(max_age_hours=4)
        major_stale = [r for r in stale if r in MAJOR_RETAILERS]
        
        for retailer in major_stale[:5]:
            try:
                await intelligence.refresh_retailer(retailer)
                await asyncio.sleep(10)  # Rate limit
            except Exception as e:
                log.warning(f"Failed to refresh {retailer}: {e}")
        
        await asyncio.sleep(1800)  # 30 minutes
```

---

## 🧠 Intelligent Decision Algorithm

### Payment Stacking Logic

Some cashback and payment methods **stack**, others conflict:

```python
STACKING_RULES = {
    # Cashback platforms generally don't stack with each other
    ("rakuten", "topcashback"): "conflict",
    ("rakuten", "honey"): "conflict",
    
    # But cashback CAN stack with:
    ("rakuten", "credit_card"): "stack",  # CC rewards
    ("topcashback", "paypal"): "stack",   # PayPal cashback
    
    # PayPal cashback stacks with most things
    ("paypal", "credit_card"): "stack",
    ("paypal", "promo_code"): "stack",
    
    # Promo codes stack with cashback
    ("promo_code", "rakuten"): "stack",
    ("promo_code", "credit_card"): "stack",
}
```

### Strategy Ranking Algorithm

```python
def rank_strategies(
    deals: RetailerDeals,
    amount: float,
    card_wallet: Optional[CardWallet],
) -> list[StrategyOption]:
    """
    Generate and rank all possible savings strategies.
    
    Algorithm:
    1. Generate all valid combinations of:
       - Cashback platform (one only)
       - Promo code (best stackable)
       - Credit card (from wallet)
       - Payment method (if bonus available)
    
    2. Filter out conflicting combinations
    
    3. Calculate effective savings for each
    
    4. Rank by total savings descending
    """
    strategies = []
    
    # Try each cashback platform
    for cashback in deals.cashback_offers:
        # With each credit card
        for card in (card_wallet.cards if card_wallet else [None]):
            # With each payment method
            for payment in [None, "paypal", "venmo"]:
                # Calculate if stackable
                if not _is_stackable(cashback, card, payment):
                    continue
                
                # Find best promo that stacks
                best_promo = _find_best_stackable_promo(
                    deals.promo_codes, 
                    cashback,
                )
                
                # Calculate totals
                option = _calculate_strategy_option(
                    amount=amount,
                    cashback=cashback,
                    promo=best_promo,
                    card=card,
                    payment=payment,
                    payment_bonus=_get_payment_bonus(deals, payment),
                )
                strategies.append(option)
    
    # Sort by total savings
    strategies.sort(key=lambda s: s.total_savings_amount, reverse=True)
    return strategies
```

---

## 🔌 Integration Points

### 1. CashbackMonitor Integration

```python
# In CashbackMonitor.find_best_cashback_and_promos()

async def find_best_cashback_and_promos(self, merchant: str) -> MerchantCashback:
    # Check RetailerIntelligence first
    if self.intelligence:
        deals = await self.intelligence.get_deals(merchant)
        if deals.is_fresh:
            return _convert_to_merchant_cashback(deals)
    
    # Fall back to live scrape
    result = await self._scrape_all_platforms(merchant)
    
    # Save to intelligence for next time
    if self.intelligence:
        await self.intelligence._save_scraped_data(merchant, result)
    
    return result
```

### 2. NetPriceOptimizer Integration

```python
# In NetPriceOptimizer._calculate_savings()

async def _calculate_savings(self, product: ProductInfo) -> RetailerOption:
    retailer = product.retailer
    
    # Use intelligent strategy
    strategy = await self.intelligence.get_best_strategy(
        retailer=retailer,
        purchase_amount=product.price,
        card_wallet=self.card_wallet,
    )
    
    savings = SavingsBreakdown(
        product_price=product.price,
        cashback_platform=strategy.recommended_cashback.platform if strategy.recommended_cashback else None,
        cashback_percent=strategy.max_cashback_percent,
        cashback_amount=product.price * (strategy.max_cashback_percent / 100),
        credit_card_name=strategy.recommended_card,
        credit_card_rewards=product.price * (strategy.max_cc_rewards / 100),
        coupon_code=strategy.recommended_promo.code if strategy.recommended_promo else None,
        coupon_savings=strategy.max_promo_value,
    )
    
    return RetailerOption(
        product=product,
        savings=savings,
        steps=strategy.steps,
        all_strategies=strategy.all_strategies,  # NEW: all options
    )
```

### 3. API Response Enhancement

```python
# New API endpoint: GET /api/v1/retailer/{name}/deals

@app.get("/api/v1/retailer/{name}/deals")
async def get_retailer_deals(name: str) -> RetailerDealsResponse:
    """Get all cashback and promo deals for a retailer."""
    deals = await intelligence.get_deals(name)
    return RetailerDealsResponse(
        retailer=deals.retailer,
        cashback_offers=[o.to_dict() for o in deals.cashback_offers],
        promo_codes=[p.to_dict() for p in deals.promo_codes],
        best_cashback=deals.best_cashback.to_dict() if deals.best_cashback else None,
        best_promo=deals.best_promo.to_dict() if deals.best_promo else None,
        cached_at=deals.cached_at.isoformat(),
        is_fresh=deals.is_fresh,
    )
```

---

## 📁 File Structure

```
intelligence-core/
├── retailer/                    # NEW MODULE
│   ├── __init__.py
│   ├── intelligence.py          # RetailerIntelligence class
│   ├── database.py              # SQLite wrapper
│   ├── cache.py                 # Redis cache layer
│   ├── strategy.py              # Decision algorithm
│   ├── models.py                # Data classes
│   └── worker.py                # Background refresh
├── cashback/
│   └── monitor.py               # Update to use intelligence
├── optimizer/
│   └── net_price.py             # Update to use intelligence
└── data/
    └── retailers.db             # SQLite database file
```

---

## 🚀 Implementation Plan

### Phase 1: Database Layer (2-3 hours)
1. Create `intelligence-core/retailer/database.py` with SQLite wrapper
2. Create schema migration logic
3. Implement CRUD operations for retailers, offers, promos

### Phase 2: Cache Layer (1-2 hours)
1. Create `intelligence-core/retailer/cache.py` with Redis wrapper
2. Implement TTL-based caching with tier support
3. Add cache invalidation logic

### Phase 3: Intelligence Class (2-3 hours)
1. Create `intelligence-core/retailer/intelligence.py`
2. Implement `get_deals()` with cache/DB fallback
3. Implement `refresh_retailer()` with scraper integration

### Phase 4: Strategy Engine (2-3 hours)
1. Create `intelligence-core/retailer/strategy.py`
2. Implement stacking rules
3. Implement `get_best_strategy()` with ranking

### Phase 5: Integration (1-2 hours)
1. Update `CashbackMonitor` to use intelligence
2. Update `NetPriceOptimizer` to use intelligent strategies
3. Add new API endpoints

### Phase 6: Testing & Deployment (1-2 hours)
1. Add unit tests
2. Update Docker volumes for SQLite persistence
3. Rebuild and test containers

---

## ✅ Acceptance Criteria

1. **Caching Works**: Second request for same retailer is < 100ms
2. **Persistence Works**: Data survives container restart
3. **All Offers Stored**: Not just best, ALL cashback offers saved
4. **All Promos Stored**: With full context (discount type, minimum, etc.)
5. **Stacking Logic**: Correctly identifies stackable combinations
6. **Background Refresh**: Major retailers stay fresh without user action
7. **API Endpoints**: New endpoints for retailer deals work

---

## 🔮 Future Enhancements

1. **ML-based promo code success prediction** based on historical data
2. **Price tracking** for retailers over time
3. **User preferences** for cashback platform (e.g., prefer Rakuten)
4. **Mobile push notifications** for elevated rate alerts
5. **Seasonal pattern detection** (holiday sales, quarterly rotations)
