"""
Cashback & Promo Code Monitor for SSIP
Checks cashback rates AND promo codes across Rakuten, Honey, TopCashback, and other platforms.
Finds the best cashback offer and available promo codes for any retailer.

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
class PromoCode:
    """A promo/coupon code from a platform."""
    platform: CashbackPlatform
    merchant: str
    code: str
    description: str = ""
    
    # Discount info
    discount_percent: Optional[float] = None  # e.g., 20 for 20% off
    discount_amount: Optional[float] = None   # e.g., $10 off
    minimum_purchase: Optional[float] = None  # e.g., $50 minimum
    
    # Metadata
    expires: Optional[str] = None
    verified: bool = False
    success_rate: Optional[float] = None  # e.g., 85% success
    last_used: Optional[str] = None
    affiliate_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["platform"] = self.platform.value
        return result
    
    @property
    def effective_value(self) -> float:
        """Estimated value for comparison (assume $100 purchase)."""
        if self.discount_percent:
            return self.discount_percent
        if self.discount_amount:
            return self.discount_amount
        return 0.0


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
    promo_codes: list[PromoCode] = field(default_factory=list)
    best_offer: Optional[CashbackOffer] = None
    best_promo: Optional[PromoCode] = None
    checked_at: Optional[str] = None
    
    def __post_init__(self):
        self._update_best()
    
    def _update_best(self):
        """Update the best offer and promo based on effective rate."""
        if self.offers:
            self.best_offer = max(self.offers, key=lambda o: o.effective_rate)
        if self.promo_codes:
            self.best_promo = max(self.promo_codes, key=lambda p: p.effective_value)
    
    def add_offer(self, offer: CashbackOffer):
        """Add an offer and update best."""
        self.offers.append(offer)
        self._update_best()
    
    def add_promo(self, promo: PromoCode):
        """Add a promo code and update best."""
        self.promo_codes.append(promo)
        self._update_best()
    
    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "offers": [o.to_dict() for o in self.offers],
            "promo_codes": [p.to_dict() for p in self.promo_codes],
            "best_offer": self.best_offer.to_dict() if self.best_offer else None,
            "best_promo": self.best_promo.to_dict() if self.best_promo else None,
            "checked_at": self.checked_at,
            "total_platforms": len(self.offers),
            "total_promos": len(self.promo_codes),
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
    
    async def find_best_cashback(
        self,
        merchant: str,
        platforms: Optional[list[CashbackPlatform]] = None,
    ) -> MerchantCashback:
        """
        Find the best cashback offer for a merchant across all platforms.
        
        Args:
            merchant: Merchant/store name (e.g., "Amazon", "Target")
            platforms: Specific platforms to check (default: all configured)
            
        Returns:
            MerchantCashback with all offers and best offer highlighted
        """
        # Check cache first
        cached = self._get_cached(merchant)
        if cached:
            return cached
        
        platforms_to_check = platforms or self.platforms
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
        
        for offers in results:
            for offer in offers:
                merchant_cashback.add_offer(offer)
        
        # Cache the result (even if empty - prevents hammering sites)
        self._set_cached(merchant, merchant_cashback)
        
        return merchant_cashback
    
    async def find_best_cashback_and_promos(
        self,
        merchant: str,
        platforms: Optional[list[CashbackPlatform]] = None,
    ) -> MerchantCashback:
        """
        Find the best cashback offer AND promo codes for a merchant.
        
        Args:
            merchant: Merchant/store name (e.g., "Amazon", "Target")
            platforms: Specific platforms to check (default: all configured)
            
        Returns:
            MerchantCashback with all offers, promo codes, and best highlighted
        """
        logger.info(f"=== Starting cashback+promo search for '{merchant}' ===")
        
        # Check cache first
        cached = self._get_cached(merchant)
        if cached and cached.promo_codes:  # Only use cache if it has promo data
            logger.debug(f"Using cached result for '{merchant}'")
            return cached
        
        platforms_to_check = platforms or self.platforms
        logger.info(f"Checking {len(platforms_to_check)} platforms: {[p.value for p in platforms_to_check]}")
        
        client = await self._get_client()
        
        # Query all platforms for cashback AND promos in parallel
        cashback_tasks = []
        promo_tasks = []
        
        for platform in platforms_to_check:
            scraper = self._scrapers.get(platform)
            if scraper:
                logger.debug(f"Adding scraper task for {platform.value}")
                cashback_tasks.append(self._safe_scrape(scraper, merchant, client, platform))
                # Check if scraper has promo code method
                if hasattr(scraper, 'get_promo_codes'):
                    promo_tasks.append(self._safe_scrape_promos(scraper, merchant, client, platform))
        
        logger.debug(f"Created {len(cashback_tasks)} cashback tasks, {len(promo_tasks)} promo tasks")
        
        # Run cashback and promo scraping in parallel
        all_tasks = cashback_tasks + promo_tasks
        all_results = await asyncio.gather(*all_tasks)
        
        # Split results
        cashback_results = all_results[:len(cashback_tasks)]
        promo_results = all_results[len(cashback_tasks):]
        
        # Aggregate results
        merchant_cashback = MerchantCashback(
            merchant=merchant,
            checked_at=datetime.now().isoformat(),
        )
        
        total_offers = 0
        total_promos = 0
        
        for offers in cashback_results:
            for offer in offers:
                merchant_cashback.add_offer(offer)
                total_offers += 1
        
        for promos in promo_results:
            for promo in promos:
                merchant_cashback.add_promo(promo)
                total_promos += 1
        
        logger.info(f"=== Search complete: {total_offers} offers, {total_promos} promos for '{merchant}' ===")
        
        # Cache the result
        self._set_cached(merchant, merchant_cashback)
        
        return merchant_cashback
    
    async def _safe_scrape_promos(
        self,
        scraper,
        merchant: str,
        client: httpx.AsyncClient,
        platform: CashbackPlatform,
    ) -> list[PromoCode]:
        """Safely scrape promo codes, catching errors."""
        try:
            logger.debug(f"[{platform.value}] Fetching promo codes for '{merchant}'...")
            promos = await scraper.get_promo_codes(merchant, client)
            logger.info(f"[{platform.value}] Found {len(promos)} promo codes for '{merchant}'")
            return promos
        except Exception as e:
            logger.warning(f"[{platform.value}] Promo scrape failed for '{merchant}': {e}")
            return []
    
    async def _safe_scrape(
        self,
        scraper,
        merchant: str,
        client: httpx.AsyncClient,
        platform: CashbackPlatform,
    ) -> list[CashbackOffer]:
        """Safely scrape a platform, catching errors."""
        try:
            logger.debug(f"[{platform.value}] Searching cashback for '{merchant}'...")
            offers = await scraper.search(merchant, client)
            if offers:
                best_rate = max(o.effective_rate for o in offers) if offers else 0
                logger.info(f"[{platform.value}] ✓ Found {len(offers)} offers for '{merchant}', best: {best_rate}%")
            else:
                logger.info(f"[{platform.value}] ✗ No offers found for '{merchant}'")
            return offers
        except httpx.TimeoutException:
            logger.warning(f"[{platform.value}] Timeout for '{merchant}'")
            return []
        except httpx.ConnectError as e:
            logger.warning(f"[{platform.value}] Connection failed for '{merchant}': {e}")
            return []
        except Exception as e:
            logger.warning(f"[{platform.value}] Scrape failed for '{merchant}': {type(e).__name__}: {e}")
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
