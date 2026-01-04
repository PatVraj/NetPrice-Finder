"""
Cashback Monitor for SSIP
Checks cashback rates across Rakuten, Honey, TopCashback, and other platforms.
Finds the best cashback offer for any retailer.

The scraping logic for each platform is now modularized in the scrapers/ package.
"""

import os
import re
import json
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import quote_plus

import httpx

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Type checking imports (avoid circular imports)
if TYPE_CHECKING:
    from ..retailer.intelligence import RetailerIntelligence

# Import modular scrapers
from .scrapers import (
    RakutenScraper,
    TopCashbackScraper,
    HoneyScraper,
    BeFrugalScraper,
    SwagbucksScraper,
)


# =============================================================================
# Configuration
# =============================================================================

# Scraper engine for sites that need browser rendering
SCRAPER_HOST = os.getenv("SCRAPER_HOST", "http://scraper-engine:8000")

# Cache TTL for cashback rates (they don't change frequently)
CACHE_TTL_HOURS = int(os.getenv("CASHBACK_CACHE_TTL", "6"))


class CashbackPlatform(Enum):
    """Supported cashback platforms."""
    RAKUTEN = "rakuten"
    HONEY = "honey"
    TOPCASHBACK = "topcashback"
    BEFRUGAL = "befrugal"
    SWAGBUCKS = "swagbucks"
    IBOTTA = "ibotta"
    RETAILMENOT = "retailmenot"
    DOSH = "dosh"


@dataclass
class CashbackOffer:
    """A cashback offer from a platform."""
    platform: CashbackPlatform
    merchant: str
    merchant_url: Optional[str] = None
    
    # Cashback rate
    cashback_percent: Optional[float] = None  # e.g., 5.0 for 5%
    cashback_fixed: Optional[float] = None    # e.g., $10 flat
    cashback_text: str = ""                   # Original text like "Up to 10%"
    
    # Offer details
    category: Optional[str] = None
    terms: Optional[str] = None
    expires: Optional[str] = None
    is_elevated: bool = False  # Special/boosted rate
    
    # Affiliate link
    affiliate_url: Optional[str] = None
    
    # Metadata
    last_updated: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["platform"] = self.platform.value
        return result
    
    @property
    def effective_rate(self) -> float:
        """Get the effective cashback rate for comparison."""
        if self.cashback_percent:
            return self.cashback_percent
        # For fixed amounts, estimate as percentage of $100 purchase
        if self.cashback_fixed:
            return self.cashback_fixed  # Treat as equivalent percentage
        return 0.0


@dataclass
class MerchantCashback:
    """Aggregated cashback info for a merchant across all platforms."""
    merchant: str
    offers: list[CashbackOffer] = field(default_factory=list)
    best_offer: Optional[CashbackOffer] = None
    checked_at: Optional[str] = None
    
    # Cache metadata (set by find_best_cashback)
    _from_cache: bool = field(default=False, repr=False)
    _cache_age_seconds: float = field(default=0.0, repr=False)
    
    def __post_init__(self):
        self._update_best()
    
    def _update_best(self):
        """Update the best offer based on effective rate."""
        if self.offers:
            self.best_offer = max(self.offers, key=lambda o: o.effective_rate)
    
    def add_offer(self, offer: CashbackOffer):
        """Add an offer and update best."""
        self.offers.append(offer)
        self._update_best()
    
    def set_cache_metadata(self, from_cache: bool, age_seconds: float = 0.0):
        """Set cache metadata for this result."""
        self._from_cache = from_cache
        self._cache_age_seconds = age_seconds
    
    @property
    def from_cache(self) -> bool:
        """Whether this result came from cache."""
        return self._from_cache
    
    @property
    def cache_age_seconds(self) -> float:
        """Age of cache in seconds (0 if fresh scrape)."""
        return self._cache_age_seconds
    
    @property
    def cache_age_human(self) -> str:
        """Human-readable cache age (e.g., '2 hours ago')."""
        if not self._from_cache:
            return "Just scraped"
        
        age = self._cache_age_seconds
        if age < 60:
            return "Just updated"
        elif age < 3600:
            minutes = int(age / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif age < 86400:
            hours = int(age / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(age / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
    
    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "offers": [o.to_dict() for o in self.offers],
            "best_offer": self.best_offer.to_dict() if self.best_offer else None,
            "checked_at": self.checked_at,
            "total_platforms": len(self.offers),
            "from_cache": self._from_cache,
            "cache_age_seconds": self._cache_age_seconds,
            "last_updated": self.cache_age_human,
        }


# =============================================================================
# Rate Parsing Utilities
# =============================================================================

def parse_cashback_rate(text: str) -> tuple[Optional[float], Optional[float], str]:
    """
    Parse cashback rate from text like "5% Cash Back" or "Up to 10%".
    
    Returns:
        Tuple of (percent, fixed_amount, original_text)
    """
    if not text:
        return None, None, ""
    
    text = text.strip()
    original = text
    
    # Remove common prefixes
    text_lower = text.lower()
    for prefix in ["up to ", "earn ", "get ", "save "]:
        if text_lower.startswith(prefix):
            text = text[len(prefix):]
            text_lower = text.lower()
    
    # Try to find percentage
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if percent_match:
        return float(percent_match.group(1)), None, original
    
    # Try to find fixed dollar amount
    dollar_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
    if dollar_match:
        return None, float(dollar_match.group(1)), original
    
    return None, None, original


# =============================================================================
# Platform-Specific Scrapers (now in scrapers/ package)
# =============================================================================
# The individual scraper classes have been refactored into separate modules:
#   - scrapers/rakuten.py      -> RakutenScraper
#   - scrapers/topcashback.py  -> TopCashbackScraper
#   - scrapers/honey.py        -> HoneyScraper
#   - scrapers/befrugal.py     -> BeFrugalScraper
#   - scrapers/swagbucks.py    -> SwagbucksScraper
# =============================================================================


# =============================================================================
# Cashback Monitor (Main Class)
# =============================================================================

class CashbackMonitor:
    """
    Monitor cashback rates across multiple platforms.
    
    Usage:
        async with CashbackMonitor() as monitor:
            result = await monitor.find_best_cashback("Amazon")
            print(f"Best: {result.best_offer.platform} - {result.best_offer.cashback_text}")
    
    For persistent caching across restarts, use with RetailerIntelligence:
        intelligence = RetailerIntelligence()
        monitor = CashbackMonitor(intelligence=intelligence)
    """
    
    def __init__(
        self,
        platforms: Optional[list[CashbackPlatform]] = None,
        timeout: float = 30.0,
        cache_enabled: bool = True,
        intelligence: Optional["RetailerIntelligence"] = None,
    ):
        """
        Initialize the cashback monitor.
        
        Args:
            platforms: List of platforms to check (default: all)
            timeout: HTTP request timeout
            cache_enabled: Whether to cache results (in-memory)
            intelligence: Optional RetailerIntelligence for persistent caching
        """
        self.platforms = platforms or list(CashbackPlatform)
        self.timeout = timeout
        self.cache_enabled = cache_enabled
        self.intelligence = intelligence
        
        # Initialize scrapers
        self._scrapers = {
            CashbackPlatform.RAKUTEN: RakutenScraper(),
            CashbackPlatform.HONEY: HoneyScraper(),
            CashbackPlatform.TOPCASHBACK: TopCashbackScraper(),
            CashbackPlatform.BEFRUGAL: BeFrugalScraper(),
            CashbackPlatform.SWAGBUCKS: SwagbucksScraper(),
        }
        
        # In-memory cache (backup if intelligence not available)
        self._cache: dict[str, tuple[MerchantCashback, datetime]] = {}
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=10),
                follow_redirects=True,
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    def _get_cached(self, merchant: str) -> Optional[MerchantCashback]:
        """Get cached result if still valid."""
        if not self.cache_enabled:
            return None
        
        key = merchant.lower().strip()
        if key in self._cache:
            result, cached_at = self._cache[key]
            if datetime.now() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
                return result
            else:
                del self._cache[key]
        return None
    
    def _set_cached(self, merchant: str, result: MerchantCashback):
        """Cache a result."""
        if self.cache_enabled:
            key = merchant.lower().strip()
            self._cache[key] = (result, datetime.now())
    
    def _convert_stored_offer(self, stored_offer, merchant: str) -> CashbackOffer:
        """Convert a StoredCashbackOffer to a CashbackOffer."""
        try:
            platform = CashbackPlatform(stored_offer.platform.lower())
        except ValueError:
            platform = CashbackPlatform.RAKUTEN  # fallback
        
        return CashbackOffer(
            platform=platform,
            merchant=merchant,
            cashback_percent=stored_offer.cashback_percent,
            cashback_fixed=stored_offer.cashback_fixed,
            cashback_text=stored_offer.cashback_text or f"{stored_offer.cashback_percent}% Cash Back",
            category=stored_offer.category,
            is_elevated=stored_offer.is_elevated,
            terms=stored_offer.terms,
            affiliate_url=stored_offer.affiliate_url,
            confidence=stored_offer.confidence or 1.0,
        )
    
    async def _get_from_intelligence_cache(self, merchant: str) -> Optional[MerchantCashback]:
        """Try to get cashback data from RetailerIntelligence cache (Redis/SQLite)."""
        if not self.intelligence:
            return None
        
        try:
            deals = await self.intelligence.get_deals(merchant, force_refresh=False)
            if not deals or not deals.cashback_offers:
                return None
            
            # Convert RetailerDeals to MerchantCashback
            merchant_cashback = MerchantCashback(
                merchant=merchant,
                checked_at=deals.last_scraped_at.isoformat() if deals.last_scraped_at else datetime.now().isoformat(),
            )
            
            # Track cache metadata using helper
            cache_age = (
                (datetime.now() - deals.last_scraped_at).total_seconds()
                if deals.last_scraped_at else 0
            )
            merchant_cashback.set_cache_metadata(from_cache=True, age_seconds=cache_age)
            
            for stored_offer in deals.cashback_offers:
                offer = self._convert_stored_offer(stored_offer, merchant)
                merchant_cashback.add_offer(offer)
            
            logger.info(f"[CACHE HIT] {merchant}: {len(deals.cashback_offers)} offers (age: {cache_age:.0f}s)")
            return merchant_cashback
            
        except Exception as e:
            logger.warning(f"[CACHE] RetailerIntelligence lookup failed for {merchant}: {e}")
            return None
    
    async def _scrape_all_platforms(
        self, merchant: str, platforms_to_check: list[CashbackPlatform]
    ) -> MerchantCashback:
        """Scrape all platforms and aggregate results."""
        client = await self._get_client()
        
        # Query all platforms in parallel
        tasks = []
        for platform in platforms_to_check:
            scraper = self._scrapers.get(platform)
            if scraper:
                tasks.append(self._safe_scrape(scraper, merchant, client, platform))
        
        results = await asyncio.gather(*tasks)
        
        # Aggregate results
        merchant_cashback = MerchantCashback(
            merchant=merchant,
            checked_at=datetime.now().isoformat(),
        )
        merchant_cashback.set_cache_metadata(from_cache=False, age_seconds=0)
        
        for offers in results:
            for offer in offers:
                merchant_cashback.add_offer(offer)
        
        return merchant_cashback
    
    async def find_best_cashback(
        self,
        merchant: str,
        platforms: Optional[list[CashbackPlatform]] = None,
        force_refresh: bool = False,
    ) -> MerchantCashback:
        """
        Find the best cashback offer for a merchant across all platforms.
        
        If RetailerIntelligence is provided, uses persistent SQLite/Redis cache.
        Otherwise, uses in-memory cache.
        
        Args:
            merchant: Merchant/store name (e.g., "Amazon", "Target")
            platforms: Specific platforms to check (default: all configured)
            force_refresh: Force fresh scrape (bypass cache)
            
        Returns:
            MerchantCashback with all offers and best offer highlighted
        """
        # 1. Try RetailerIntelligence cache first (persistent SQLite/Redis)
        if not force_refresh:
            cached_result = await self._get_from_intelligence_cache(merchant)
            if cached_result:
                return cached_result
        
        # 2. Check in-memory cache (fallback if no intelligence)
        if not self.intelligence:
            cached = self._get_cached(merchant)
            if cached:
                cached.set_cache_metadata(from_cache=True, age_seconds=cached.cache_age_seconds)
                return cached
        
        # 3. Fresh scrape required
        logger.info(f"[SCRAPING] Fresh scrape for {merchant}...")
        platforms_to_check = platforms or self.platforms
        merchant_cashback = await self._scrape_all_platforms(merchant, platforms_to_check)
        
        # 4. Store in RetailerIntelligence (persistent cache)
        if self.intelligence and merchant_cashback.offers:
            try:
                await self._store_to_intelligence(merchant, merchant_cashback)
                logger.info(f"[CACHE] Stored {len(merchant_cashback.offers)} offers for {merchant}")
            except Exception as e:
                logger.warning(f"[CACHE] Failed to store offers for {merchant}: {e}")
        
        # 5. Also cache in-memory (quick fallback)
        self._set_cached(merchant, merchant_cashback)
        
        return merchant_cashback
    
    async def _store_to_intelligence(self, merchant: str, cashback: MerchantCashback):
        """Store scraped cashback data in RetailerIntelligence."""
        if not self.intelligence:
            return
        
        from ..retailer.models import StoredCashbackOffer, normalize_retailer_name
        
        # Get or create retailer
        db_retailer = self.intelligence.db.get_or_create_retailer(merchant)
        
        # Convert CashbackOffer to StoredCashbackOffer and store
        stored_offers = []
        for offer in cashback.offers:
            stored = StoredCashbackOffer(
                retailer_id=db_retailer.id,
                platform=offer.platform.value,
                cashback_percent=offer.cashback_percent,
                cashback_fixed=offer.cashback_fixed,
                cashback_text=offer.cashback_text,
                category=offer.category,
                is_elevated=offer.is_elevated,
                terms=offer.terms,
                affiliate_url=offer.affiliate_url,
                confidence=offer.confidence,
                scraped_at=datetime.now(),
            )
            stored_offers.append(stored)
        
        # Store in database
        self.intelligence.db.save_cashback_offers(db_retailer.id, stored_offers)
        
        # Warm Redis cache using proper serialization
        await self.intelligence.cache.set_deals(
            normalize_retailer_name(merchant),
            {
                "retailer": merchant,
                "cashback_offers": [o.to_dict() for o in stored_offers],
                "_cached_at": datetime.now().isoformat(),
                "_tier": db_retailer.tier.value if db_retailer.tier else "standard",
            },
            tier=db_retailer.tier.value if db_retailer.tier else "standard",
        )
    
    async def _safe_scrape(
        self,
        scraper,
        merchant: str,
        client: httpx.AsyncClient,
        platform: CashbackPlatform,
    ) -> list[CashbackOffer]:
        """Safely scrape a platform, catching errors."""
        platform_name = platform.value.title()
        try:
            logger.info(f"[{platform_name}] Searching cashback for {merchant}...")
            offers = await scraper.search(merchant, client)
            if offers:
                best_rate = max(o.effective_rate for o in offers) if offers else 0
                logger.info(f"[{platform_name}] ✓ Found: {best_rate}% Cash Back for {merchant}")
            else:
                logger.info(f"[{platform_name}] ✗ No cashback for {merchant}")
            return offers
        except httpx.TimeoutException:
            logger.warning(f"[{platform_name}] ⏱ Timeout while searching {merchant}")
            return []
        except httpx.ConnectError as e:
            logger.warning(f"[{platform_name}] ⚠ Connection failed for {merchant}")
            return []
        except Exception as e:
            logger.warning(f"[{platform_name}] ⚠ Error searching {merchant}: {type(e).__name__}")
            return []
    
    async def compare_merchants(
        self,
        merchants: list[str],
    ) -> dict[str, MerchantCashback]:
        """
        Compare cashback for multiple merchants.
        
        Args:
            merchants: List of merchant names
            
        Returns:
            Dict mapping merchant name to MerchantCashback
        """
        tasks = [self.find_best_cashback(m) for m in merchants]
        results = await asyncio.gather(*tasks)
        return dict(zip(merchants, results))
    
    async def get_top_offers(
        self,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[CashbackOffer]:
        """
        Get top cashback offers (requires pre-populated cache or known merchants).
        
        This is a placeholder - real implementation would scrape "featured" sections.
        """
        # Popular merchants to check
        popular = [
            "Amazon", "Target", "Walmart", "Best Buy", "Macy's",
            "Nike", "Adidas", "Sephora", "Ulta", "Home Depot",
        ]
        
        if category:
            # Filter by category (would need merchant-category mapping)
            pass
        
        all_offers = []
        for merchant in popular[:limit]:
            result = await self.find_best_cashback(merchant)
            if result.best_offer:
                all_offers.append(result.best_offer)
        
        # Sort by effective rate
        all_offers.sort(key=lambda o: o.effective_rate, reverse=True)
        return all_offers[:limit]


# =============================================================================
# Known Merchant Database (for quick lookups)
# =============================================================================

# Popular merchants and their typical cashback ranges
KNOWN_MERCHANTS = {
    "amazon": {
        "category": "online_shopping",
        "typical_rates": {"rakuten": 1.0, "topcashback": 1.0},
    },
    "target": {
        "category": "retail",
        "typical_rates": {"rakuten": 1.0, "topcashback": 2.0},
    },
    "walmart": {
        "category": "retail", 
        "typical_rates": {"rakuten": 2.0, "topcashback": 3.0},
    },
    "best buy": {
        "category": "electronics",
        "typical_rates": {"rakuten": 1.0, "topcashback": 1.5},
    },
    "nike": {
        "category": "clothing",
        "typical_rates": {"rakuten": 4.0, "topcashback": 6.0},
    },
    "sephora": {
        "category": "beauty",
        "typical_rates": {"rakuten": 4.0, "topcashback": 5.0},
    },
    "home depot": {
        "category": "home_improvement",
        "typical_rates": {"rakuten": 2.0, "topcashback": 2.5},
    },
    "uber eats": {
        "category": "food_delivery",
        "typical_rates": {"rakuten": 2.5, "topcashback": 3.0},
    },
    "doordash": {
        "category": "food_delivery",
        "typical_rates": {"rakuten": 2.0, "topcashback": 2.5},
    },
    "instacart": {
        "category": "groceries",
        "typical_rates": {"rakuten": 1.5, "topcashback": 2.0},
    },
}


def get_known_merchant_info(merchant: str) -> Optional[dict]:
    """Get known info about a merchant."""
    key = merchant.lower().strip()
    return KNOWN_MERCHANTS.get(key)


# =============================================================================
# Convenience Functions
# =============================================================================

async def find_cashback(merchant: str) -> MerchantCashback:
    """Quick helper to find cashback for a merchant."""
    async with CashbackMonitor() as monitor:
        return await monitor.find_best_cashback(merchant)


async def compare_cashback(merchants: list[str]) -> dict[str, MerchantCashback]:
    """Quick helper to compare cashback for multiple merchants."""
    async with CashbackMonitor() as monitor:
        return await monitor.compare_merchants(merchants)


async def get_best_platform(merchant: str) -> Optional[tuple[str, float]]:
    """
    Get the best cashback platform for a merchant.
    
    Returns:
        Tuple of (platform_name, cashback_percent) or None
    """
    result = await find_cashback(merchant)
    if result.best_offer:
        return (result.best_offer.platform.value, result.best_offer.effective_rate)
    return None


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python monitor.py <merchant_name>")
            print("Example: python monitor.py Amazon")
            sys.exit(1)
        
        merchant = " ".join(sys.argv[1:])
        print(f"🔍 Searching cashback for: {merchant}\n")
        
        async with CashbackMonitor() as monitor:
            result = await monitor.find_best_cashback(merchant)
        
        print(f"Found {len(result.offers)} offers:\n")
        
        for offer in sorted(result.offers, key=lambda o: o.effective_rate, reverse=True):
            rate = f"{offer.cashback_percent}%" if offer.cashback_percent else f"${offer.cashback_fixed}"
            elevated = " ⭐ ELEVATED" if offer.is_elevated else ""
            print(f"  {offer.platform.value.upper():15} {rate:>10} {offer.cashback_text}{elevated}")
        
        if result.best_offer:
            print(f"\n✅ Best offer: {result.best_offer.platform.value.upper()} - {result.best_offer.cashback_text}")
            if result.best_offer.affiliate_url:
                print(f"   Link: {result.best_offer.affiliate_url}")
    
    asyncio.run(main())
