"""
Cashback Monitor for SSIP
Checks cashback rates across Rakuten, Honey, TopCashback, and other platforms.
Finds the best cashback offer for any retailer.
"""

import os
import re
import json
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import quote_plus

import httpx


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
    
    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "offers": [o.to_dict() for o in self.offers],
            "best_offer": self.best_offer.to_dict() if self.best_offer else None,
            "checked_at": self.checked_at,
            "total_platforms": len(self.offers),
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
# Platform-Specific Scrapers
# =============================================================================

class RakutenScraper:
    """Scrape cashback rates from Rakuten (formerly Ebates)."""
    
    BASE_URL = "https://www.rakuten.com"
    SEARCH_URL = "https://www.rakuten.com/s"
    
    # Rakuten has a semi-public API for their store data
    API_URL = "https://www.rakuten.com/api/stores"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Search Rakuten for a merchant."""
        offers = []
        
        try:
            # Try the API first (faster and more reliable)
            params = {"term": merchant, "limit": 5}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            
            response = await client.get(
                f"{self.API_URL}/search",
                params=params,
                headers=headers,
            )
            
            if response.status_code == 200:
                data = response.json()
                stores = data.get("stores", data.get("results", []))
                
                for store in stores[:3]:  # Top 3 results
                    name = store.get("name", store.get("storeName", ""))
                    cashback_text = store.get("cashBack", store.get("rebate", ""))
                    
                    if not name:
                        continue
                    
                    percent, fixed, original = parse_cashback_rate(str(cashback_text))
                    
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.RAKUTEN,
                        merchant=name,
                        merchant_url=store.get("url", store.get("storeUrl")),
                        cashback_percent=percent,
                        cashback_fixed=fixed,
                        cashback_text=original or str(cashback_text),
                        category=store.get("category"),
                        affiliate_url=f"{self.BASE_URL}/{store.get('slug', name.lower().replace(' ', '-'))}",
                        is_elevated=store.get("isElevated", False) or store.get("isDoubleCashBack", False),
                        last_updated=datetime.now().isoformat(),
                    ))
            
        except Exception as e:
            # Fallback: try HTML scraping via scraper service
            offers = await self._scrape_html(merchant, client)
        
        return offers
    
    async def _scrape_html(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Fallback HTML scraping via scraper engine."""
        offers = []
        
        try:
            # Use our scraper engine to render the page
            response = await client.post(
                f"{SCRAPER_HOST}/navigate",
                json={"url": f"{self.SEARCH_URL}?term={quote_plus(merchant)}"},
                timeout=30.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                # Parse HTML content for cashback rates
                # This is a simplified version - real implementation would use BeautifulSoup
                html = data.get("html", "")
                
                # Look for store cards with cashback info
                # Pattern: store name and cashback rate
                store_pattern = r'data-store-name="([^"]+)"[^>]*>.*?(\d+(?:\.\d+)?%\s*Cash\s*Back)'
                matches = re.findall(store_pattern, html, re.IGNORECASE | re.DOTALL)
                
                for name, rate in matches[:3]:
                    percent, fixed, original = parse_cashback_rate(rate)
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.RAKUTEN,
                        merchant=name,
                        cashback_percent=percent,
                        cashback_fixed=fixed,
                        cashback_text=original,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.8,  # Lower confidence for HTML scraping
                    ))
                    
        except Exception:
            pass
        
        return offers


class HoneyScraper:
    """Scrape cashback rates from Honey (PayPal Honey)."""
    
    # Honey uses a different approach - browser extension primarily
    # But they have merchant pages that can be scraped
    BASE_URL = "https://www.joinhoney.com"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Search Honey for merchant cashback/rewards."""
        offers = []
        
        try:
            # Honey's merchant pages follow a pattern
            slug = merchant.lower().replace(" ", "-").replace("'", "")
            url = f"{self.BASE_URL}/shop/{slug}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            if response.status_code == 200:
                html = response.text
                
                # Look for Honey Gold rewards
                # Honey uses "Honey Gold" instead of direct cashback
                gold_pattern = r'(\d+(?:\.\d+)?%?)\s*(?:Honey\s*Gold|Gold\s*rewards?|back)'
                matches = re.findall(gold_pattern, html, re.IGNORECASE)
                
                if matches:
                    rate_text = matches[0]
                    percent, fixed, original = parse_cashback_rate(rate_text)
                    
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.HONEY,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_fixed=fixed,
                        cashback_text=f"{original} Honey Gold" if original else "Honey Gold rewards",
                        affiliate_url=url,
                        terms="Honey Gold can be redeemed for gift cards",
                        last_updated=datetime.now().isoformat(),
                        confidence=0.7,
                    ))
                    
        except Exception:
            pass
        
        return offers


class TopCashbackScraper:
    """Scrape cashback rates from TopCashback using their search API."""
    
    BASE_URL = "https://www.topcashback.com"
    # TopCashback has a JSON API for search that's more reliable than scraping
    SEARCH_API = "https://www.topcashback.com/ajax/merchant/search"
    MERCHANT_URL = "https://www.topcashback.com/{slug}"
    
    # Scraper engine for browser-based scraping when needed
    SCRAPER_HOST = os.getenv("SCRAPER_HOST", "http://scraper-engine:5000")
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Search TopCashback for merchant rates with verification."""
        offers = []
        
        try:
            # First, try the search to find exact merchant match
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.topcashback.com/",
            }
            
            # Try the search API first
            response = await client.get(
                self.SEARCH_API,
                params={"term": merchant, "maxResults": 5},
                headers=headers,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    # API returns list of merchants with cashback info
                    merchants = data if isinstance(data, list) else data.get("merchants", [])
                    
                    for m in merchants:
                        name = m.get("name", m.get("merchantName", ""))
                        # Verify it's actually the merchant we're looking for
                        if self._is_merchant_match(merchant, name):
                            rate = m.get("cashback", m.get("rate", m.get("cashbackRate", "")))
                            url = m.get("url", m.get("merchantUrl", ""))
                            
                            if rate:
                                percent, fixed, text = parse_cashback_rate(str(rate))
                                if percent or fixed:
                                    offers.append(CashbackOffer(
                                        platform=CashbackPlatform.TOPCASHBACK,
                                        merchant=name,
                                        cashback_percent=percent,
                                        cashback_fixed=fixed,
                                        cashback_text=text or f"Up to {rate}",
                                        affiliate_url=f"{self.BASE_URL}{url}" if url.startswith("/") else url,
                                        last_updated=datetime.now().isoformat(),
                                        confidence=0.95,  # High confidence from API
                                    ))
                                    return offers  # Found verified match
                except (json.JSONDecodeError, ValueError):
                    pass  # Not JSON, try direct page
            
            # Fallback: Try direct merchant page with verification
            slug = self._make_slug(merchant)
            url = self.MERCHANT_URL.format(slug=slug)
            
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
            
            if response.status_code == 200:
                # CRITICAL: Verify this is actually the merchant page, not a 404/search page
                html = response.text
                
                # Check if page is a valid merchant page (not search results or error)
                if self._is_valid_merchant_page(html, merchant):
                    offer = self._parse_merchant_page(html, merchant, url)
                    if offer:
                        offers.append(offer)
                        
        except Exception as e:
            # Don't return false positives on error
            pass
        
        return offers
    
    def _is_merchant_match(self, search_term: str, found_name: str) -> bool:
        """Verify the found merchant actually matches what we're looking for."""
        search_lower = search_term.lower().strip()
        found_lower = found_name.lower().strip()
        
        # Exact match
        if search_lower == found_lower:
            return True
        
        # Search term is contained in found name (e.g., "Macy's" in "Macy's Department Store")
        if search_lower in found_lower:
            return True
        
        # Found name is contained in search term
        if found_lower in search_lower:
            return True
        
        # Handle common variations
        search_normalized = re.sub(r"[^a-z0-9]", "", search_lower)
        found_normalized = re.sub(r"[^a-z0-9]", "", found_lower)
        
        if search_normalized == found_normalized:
            return True
        
        if search_normalized in found_normalized or found_normalized in search_normalized:
            return True
        
        return False
    
    def _is_valid_merchant_page(self, html: str, merchant: str) -> bool:
        """
        Verify this is a valid merchant cashback page, not:
        - A search results page
        - A 404/error page
        - A completely different merchant
        """
        html_lower = html.lower()
        merchant_lower = merchant.lower()
        
        # Signs this is NOT a valid merchant page:
        invalid_indicators = [
            "page not found",
            "no results found",
            "search results for",
            "we couldn't find",
            "0 results",
            "sorry, we couldn't",
        ]
        
        for indicator in invalid_indicators:
            if indicator in html_lower:
                return False
        
        # The merchant name should appear on the page
        merchant_normalized = re.sub(r"[^a-z0-9]", "", merchant_lower)
        html_normalized = re.sub(r"[^a-z0-9]", "", html_lower)
        
        if merchant_normalized not in html_normalized:
            return False
        
        # Should have cashback-related content
        cashback_indicators = ["cash back", "cashback", "% back", "earn cash"]
        has_cashback = any(indicator in html_lower for indicator in cashback_indicators)
        
        if not has_cashback:
            return False
        
        return True
    
    def _make_slug(self, merchant: str) -> str:
        """Convert merchant name to URL slug."""
        # Common merchant name to TopCashback slug mappings
        slug_overrides = {
            "macy's": "macys",
            "macys": "macys",
            "nordstrom": "nordstrom",
            "best buy": "best-buy",
            "bestbuy": "best-buy",
            "walmart": "walmart",
            "target": "target",
            "amazon": "amazon",
            "home depot": "the-home-depot",
            "lowe's": "lowes",
            "lowes": "lowes",
            "sephora": "sephora",
            "nike": "nikecom",
            "adidas": "adidas",
        }
        
        merchant_lower = merchant.lower().strip()
        if merchant_lower in slug_overrides:
            return slug_overrides[merchant_lower]
        
        # Default: lowercase, replace spaces with hyphens
        return re.sub(r'[^a-z0-9]+', '-', merchant_lower).strip('-')
    
    def _parse_merchant_page(self, html: str, merchant: str, url: str) -> Optional[CashbackOffer]:
        """Parse TopCashback merchant page for cashback rate."""
        # TopCashback shows rate in formats like:
        # "Up to 6% Cash Back"
        # "6% Cash Back"  
        # "Up to $10 Cash Back"
        
        # Pattern for percentage cashback - look for prominent rates
        rate_patterns = [
            r'(?:Up\s*to\s*)?(\d+(?:\.\d+)?)\s*%\s*(?:Cash\s*Back|Cashback)',
            r'class="[^"]*rate[^"]*"[^>]*>(?:Up\s*to\s*)?(\d+(?:\.\d+)?)\s*%',
            r'data-rate="(\d+(?:\.\d+)?)"',
        ]
        
        for pattern in rate_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                rate = float(match.group(1))
                if 0 < rate <= 50:  # Sanity check - rates above 50% are suspicious
                    return CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_percent=rate,
                        cashback_text=f"Up to {rate}% Cash Back",
                        affiliate_url=url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.85,  # Good confidence from verified page
                    )
        
        # Pattern for fixed dollar cashback
        fixed_patterns = [
            r'(?:Up\s*to\s*)?\$(\d+(?:\.\d+)?)\s*(?:Cash\s*Back|Cashback)',
        ]
        
        for pattern in fixed_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                amount = float(match.group(1))
                if 0 < amount <= 500:  # Sanity check
                    return CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_fixed=amount,
                        cashback_text=f"Up to ${amount} Cash Back",
                        affiliate_url=url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.85,
                    )
        
        return None


class BeFrugalScraper:
    """Scrape cashback rates from BeFrugal."""
    
    BASE_URL = "https://www.befrugal.com"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Search BeFrugal for merchant rates."""
        offers = []
        
        try:
            # BeFrugal has direct merchant pages
            slug = merchant.lower().replace(" ", "-")
            url = f"{self.BASE_URL}/coupons/{slug}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            if response.status_code == 200:
                html = response.text
                
                # BeFrugal shows cashback prominently
                rate_pattern = r'(\d+(?:\.\d+)?%)\s*(?:Cash\s*Back|cashback)'
                matches = re.findall(rate_pattern, html, re.IGNORECASE)
                
                if matches:
                    percent, fixed, original = parse_cashback_rate(matches[0])
                    
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.BEFRUGAL,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_fixed=fixed,
                        cashback_text=original or matches[0],
                        affiliate_url=url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.7,
                    ))
                    
        except Exception:
            pass
        
        return offers


class SwagbucksScraper:
    """Scrape cashback rates from Swagbucks Shop."""
    
    BASE_URL = "https://www.swagbucks.com"
    SEARCH_URL = "https://www.swagbucks.com/shop/search"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list[CashbackOffer]:
        """Search Swagbucks for merchant rates."""
        offers = []
        
        try:
            params = {"q": merchant}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            
            response = await client.get(
                self.SEARCH_URL,
                params=params,
                headers=headers,
                follow_redirects=True,
            )
            
            if response.status_code == 200:
                html = response.text
                
                # Swagbucks shows "X SB per $" or "X% back"
                sb_pattern = r'(\d+)\s*SB\s*(?:per\s*\$|back)'
                percent_pattern = r'(\d+(?:\.\d+)?%)\s*back'
                
                sb_matches = re.findall(sb_pattern, html, re.IGNORECASE)
                percent_matches = re.findall(percent_pattern, html, re.IGNORECASE)
                
                if percent_matches:
                    percent, _, original = parse_cashback_rate(percent_matches[0])
                    cashback_text = original
                elif sb_matches:
                    # SB = Swagbucks, roughly 1 SB = $0.01
                    sb_per_dollar = int(sb_matches[0])
                    percent = sb_per_dollar  # Approximate as percentage
                    cashback_text = f"{sb_per_dollar} SB per $1"
                else:
                    return offers
                
                offers.append(CashbackOffer(
                    platform=CashbackPlatform.SWAGBUCKS,
                    merchant=merchant,
                    cashback_percent=percent,
                    cashback_text=cashback_text,
                    terms="Earn Swagbucks (SB) redeemable for gift cards",
                    affiliate_url=f"{self.SEARCH_URL}?q={quote_plus(merchant)}",
                    last_updated=datetime.now().isoformat(),
                    confidence=0.7,
                ))
                
        except Exception:
            pass
        
        return offers


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
    """
    
    def __init__(
        self,
        platforms: Optional[list[CashbackPlatform]] = None,
        timeout: float = 30.0,
        cache_enabled: bool = True,
    ):
        """
        Initialize the cashback monitor.
        
        Args:
            platforms: List of platforms to check (default: all)
            timeout: HTTP request timeout
            cache_enabled: Whether to cache results
        """
        self.platforms = platforms or list(CashbackPlatform)
        self.timeout = timeout
        self.cache_enabled = cache_enabled
        
        # Initialize scrapers
        self._scrapers = {
            CashbackPlatform.RAKUTEN: RakutenScraper(),
            CashbackPlatform.HONEY: HoneyScraper(),
            CashbackPlatform.TOPCASHBACK: TopCashbackScraper(),
            CashbackPlatform.BEFRUGAL: BeFrugalScraper(),
            CashbackPlatform.SWAGBUCKS: SwagbucksScraper(),
        }
        
        # In-memory cache
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
    
    async def _safe_scrape(
        self,
        scraper,
        merchant: str,
        client: httpx.AsyncClient,
        platform: CashbackPlatform,
    ) -> list[CashbackOffer]:
        """Safely scrape a platform, catching errors."""
        try:
            return await scraper.search(merchant, client)
        except Exception as e:
            # Return empty list on error, don't fail the whole search
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
