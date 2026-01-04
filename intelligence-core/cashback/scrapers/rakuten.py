"""
Rakuten Scraper
Extracts cashback rates and promo codes from Rakuten.com (formerly Ebates)
"""

import re
import logging
from datetime import datetime

import httpx

from .base import (
    BaseScraper,
    parse_cashback_rate,
)

logger = logging.getLogger(__name__)


class RakutenScraper(BaseScraper):
    """
    Scraper for Rakuten.com (formerly Ebates)
    
    Rakuten uses a semi-public API for store data, with HTML fallback.
    """
    
    PLATFORM_NAME = "rakuten"
    BASE_URL = "https://www.rakuten.com"
    API_URL = "https://www.rakuten.com/api/stores"
    
    # Slug overrides for merchants with non-standard URLs
    SLUG_OVERRIDES = {
        "nike": "nike",
        "macy's": "macys",
        "macys": "macys",
        "nordstrom": "nordstrom",
        "best buy": "bestbuy",
        "bestbuy": "bestbuy",
        "walmart": "walmart",
        "target": "target",
        "amazon": "amazon",
        "home depot": "homedepot",
        "lowe's": "lowes",
        "lowes": "lowes",
        "sephora": "sephora",
        "adidas": "adidas",
        "pandora": "pandora-jewelry",
        "pandora jewelry": "pandora-jewelry",
        "ulta": "ultabeauty",
        "ulta beauty": "ultabeauty",
        "kohl's": "kohls",
        "kohls": "kohls",
        "old navy": "oldnavy",
        "dick's sporting goods": "dickssportinggoods",
    }
    
    # Alternative slug patterns to try if the first one fails
    SLUG_ALTERNATIVES = {
        "pandora": ["pandora-jewelry", "pandora"],
        "ulta": ["ultabeauty", "ulta-beauty", "ulta"],
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Rakuten for a merchant."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
            # Strategy 1: Try the search page (most reliable for finding merchants)
            search_offers = await self._search_page(merchant, client)
            if search_offers:
                return search_offers
            
            # Strategy 2: Try the API (may be deprecated/limited)
            api_offers = await self._search_api(merchant, client)
            if api_offers:
                return api_offers
            
            # Strategy 3: Fall back to direct merchant page scraping
            browser_offers = await self._scrape_merchant_page(merchant, client)
            if browser_offers:
                return browser_offers
            browser_offers = await self._scrape_merchant_page(merchant, client)
            if browser_offers:
                return browser_offers
                
        except Exception as e:
            logger.warning(f"[{self.PLATFORM_NAME}] Error: {type(e).__name__}: {e}")
        
        return offers
    
    async def _search_page(self, merchant: str, client: httpx.AsyncClient) -> list:
        """
        Scrape the Rakuten search results page.
        
        This is the most reliable method as it shows all matching merchants
        with their current cashback rates.
        
        URL format: https://www.rakuten.com/search?term=pandora&type=suggest
        """
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        search_url = f"{self.BASE_URL}/search?term={merchant}&type=suggest"
        
        logger.debug(f"[{self.PLATFORM_NAME}] Searching via page: {search_url}")
        
        data = await self._browser_extract(
            client,
            search_url,
            {},  # No specific selectors - we'll parse body_text
            wait_for="networkidle",
        )
        
        if not data:
            logger.debug(f"[{self.PLATFORM_NAME}] Search page returned no data")
            return offers
        
        body_text = data.get("body_text", "")
        html = data.get("html", "")
        
        logger.debug(f"[{self.PLATFORM_NAME}] Search page body: {len(body_text)} chars")
        
        # Look for the merchant in the results
        # Pattern: "PANDORA Jewelry4% Onlinewas 2%2% In-Store" or "Nike8% Online"
        merchant_lower = merchant.lower()
        
        # Try to find the merchant section with rate
        # Look for patterns like "PANDORA Jewelry4% Online" or "Nike8% Onlinewas 6%"
        patterns = [
            # Merchant name followed by rate: "PANDORA Jewelry4% Online"
            rf'({re.escape(merchant)}[^0-9]*?)(\d+(?:\.\d+)?)\s*%\s*Online',
            # Rate with "was X%" elevated indicator
            rf'({re.escape(merchant)}[^0-9]*?)(\d+(?:\.\d+)?)\s*%\s*Online\s*was\s*(\d+(?:\.\d+)?)\s*%',
            # Just the rate near merchant name
            rf'{re.escape(merchant)}[^0-9]{{0,50}}(\d+(?:\.\d+)?)\s*%\s*(?:Cash\s*Back|Online)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                # Get the rate (group 2 for first pattern, or last numeric group)
                groups = match.groups()
                # Find the percentage in the groups
                for g in groups:
                    if g and re.match(r'^\d+(?:\.\d+)?$', str(g)):
                        percent = float(g)
                        if self._filter_valid_rate(percent):
                            # Check if it's an elevated rate
                            is_elevated = "was" in match.group(0).lower()
                            
                            logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (search page){' (elevated)' if is_elevated else ''}")
                            
                            offers.append(CashbackOffer(
                                platform=CashbackPlatform.RAKUTEN,
                                merchant=merchant,
                                cashback_percent=percent,
                                cashback_fixed=None,
                                cashback_text=f"{percent}% Cash Back",
                                affiliate_url=search_url,
                                last_updated=datetime.now().isoformat(),
                                is_elevated=is_elevated,
                                confidence=0.95,
                            ))
                            return offers
        
        # Fallback: look for any rate pattern if merchant name is in page
        if merchant_lower in body_text.lower():
            # Find rates in the format "X% Online" or "X% Cash Back"
            rate_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:Online|Cash\s*Back)', body_text, re.IGNORECASE)
            if rate_matches:
                # Use the first reasonable rate found near the search term
                for rate_str in rate_matches[:5]:
                    percent = float(rate_str)
                    if self._filter_valid_rate(percent):
                        logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (search fallback)")
                        offers.append(CashbackOffer(
                            platform=CashbackPlatform.RAKUTEN,
                            merchant=merchant,
                            cashback_percent=percent,
                            cashback_fixed=None,
                            cashback_text=f"{percent}% Cash Back",
                            affiliate_url=search_url,
                            last_updated=datetime.now().isoformat(),
                            confidence=0.8,
                        ))
                        return offers
        
        logger.debug(f"[{self.PLATFORM_NAME}] No matching merchant found in search results")
        return offers
    
    async def _search_api(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Try the Rakuten search API."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.rakuten.com/",
            "Origin": "https://www.rakuten.com",
        }
        
        try:
            logger.debug(f"[{self.PLATFORM_NAME}] Calling API: {self.API_URL}/search?term={merchant}")
            
            response = await client.get(
                f"{self.API_URL}/search",
                params={"term": merchant, "limit": 5},
                headers=headers,
                timeout=10.0,
            )
            
            logger.debug(f"[{self.PLATFORM_NAME}] Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                stores = data.get("stores", data.get("results", []))
                
                for store in stores[:3]:
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
                
                logger.debug(f"[{self.PLATFORM_NAME}] Found {len(offers)} offers from API")
                
            elif response.status_code != 404:
                logger.warning(f"[{self.PLATFORM_NAME}] API returned {response.status_code}")
                
        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] API failed: {e}")
        
        return offers
    
    async def _scrape_merchant_page(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Browser-based scraping via scraper engine for Rakuten."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        merchant_lower = merchant.lower().strip()
        
        # Get all slugs to try (primary + alternatives)
        slugs_to_try = self._get_all_slugs(merchant)
        
        # URL patterns to try for each slug
        url_patterns = [
            "https://www.rakuten.com/{slug}",           # Direct slug (most common)
            "https://www.rakuten.com/shop/{slug}",      # /shop/ pattern
        ]
        
        data = None
        successful_url = None
        
        # Try each slug with each URL pattern
        for slug in slugs_to_try:
            for pattern in url_patterns:
                merchant_url = pattern.format(slug=slug)
                logger.debug(f"[{self.PLATFORM_NAME}] Trying: {merchant_url}")
                
                data = await self._browser_extract(
                    client,
                    merchant_url,
                    {},  # No specific selectors needed
                    wait_for="networkidle",
                )
                
                if data:
                    body_text = data.get("body_text", "")
                    # Check if this is NOT a 404 page
                    if not self._is_not_found(body_text) and len(body_text) > 500:
                        successful_url = merchant_url
                        logger.debug(f"[{self.PLATFORM_NAME}] Found valid page at {merchant_url}")
                        break
            
            if successful_url:
                break
        
        if not data or not successful_url:
            logger.debug(f"[{self.PLATFORM_NAME}] No valid page found for '{merchant}'")
            return offers
        
        body_text = data.get("body_text", "")
        logger.debug(f"[{self.PLATFORM_NAME}] Got body_text: {len(body_text)} chars from {successful_url}")
        
        # Parse body_text for cashback rates
        patterns = [
            # "4% Online" or "X% Online" pattern (Rakuten format)
            r'(\d+(?:\.\d+)?)\s*%\s*Online',
            # "Get 6% Cash Back" pattern
            r'Get\s+(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "X% Cash Back" pattern
            r'(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "was X%" elevated rate pattern
            r'was\s+(\d+(?:\.\d+)?)\s*%',
            # "Up to X%" pattern
            r'Up\s+to\s+(\d+(?:\.\d+)?)\s*%',
        ]
        
        # Check for elevated/boosted rate
        is_elevated = any(phrase in body_text.lower() for phrase in [
            "was ", "boosted", "elevated", "hot deal", "limited time"
        ])
        
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                percent = float(match.group(1))
                # Filter valid rates (cashback rarely exceeds 25%)
                if self._filter_valid_rate(percent):
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back{' (elevated)' if is_elevated else ''}")
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.RAKUTEN,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_fixed=None,
                        cashback_text=f"{percent}% Cash Back",
                        affiliate_url=successful_url,
                        last_updated=datetime.now().isoformat(),
                        is_elevated=is_elevated,
                        confidence=0.9,
                    ))
                    break
        
        if not offers:
            logger.debug(f"[{self.PLATFORM_NAME}] No rate pattern matched for '{merchant}' in body_text")
            # Log a snippet for debugging
            if body_text:
                logger.debug(f"[{self.PLATFORM_NAME}] Body preview: {body_text[:300]}...")
        
        return offers
    
    async def get_promo_codes(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Get promo codes from Rakuten for a merchant."""
        from ..monitor import PromoCode, CashbackPlatform
        
        promos = []
        slug = self._get_slug(merchant)
        url = f"{self.BASE_URL}/{slug}/coupons"
        
        try:
            response = await client.get(
                url,
                headers=self.get_headers(),
                follow_redirects=True,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                html = response.text
                promos = self._parse_promo_codes(merchant, html, url)
                
        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Promo fetch failed: {e}")
        
        return promos
    
    def _parse_promo_codes(self, merchant: str, html: str, url: str) -> list:
        """Parse promo codes from HTML."""
        from ..monitor import PromoCode, CashbackPlatform
        
        promos = []
        seen_codes = set()
        
        code_patterns = [
            r'data-code="([A-Z0-9]+)"',
            r'code["\s:]+([A-Z0-9]{4,20})',
            r'coupon["\s:]+([A-Z0-9]{4,20})',
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for code in matches[:5]:
                code_upper = code.upper()
                if code_upper not in seen_codes and len(code_upper) >= 4:
                    seen_codes.add(code_upper)
                    
                    # Try to find description near the code
                    desc_match = re.search(
                        rf'{code}[^<]*?(\d+%?\s*off|free\s*shipping|\$\d+\s*off)',
                        html, re.IGNORECASE
                    )
                    description = desc_match.group(1) if desc_match else ""
                    
                    percent, amount = None, None
                    if '%' in description:
                        pct_match = re.search(r'(\d+)%', description)
                        if pct_match:
                            percent = float(pct_match.group(1))
                    elif '$' in description:
                        amt_match = re.search(r'\$(\d+)', description)
                        if amt_match:
                            amount = float(amt_match.group(1))
                    
                    promos.append(PromoCode(
                        platform=CashbackPlatform.RAKUTEN,
                        merchant=merchant,
                        code=code_upper,
                        description=description or f"Promo code for {merchant}",
                        discount_percent=percent,
                        discount_amount=amount,
                        affiliate_url=url,
                    ))
        
        return promos
    
    def _get_slug(self, merchant: str) -> str:
        """Get primary URL slug for merchant."""
        merchant_lower = merchant.lower().strip()
        if merchant_lower in self.SLUG_OVERRIDES:
            return self.SLUG_OVERRIDES[merchant_lower]
        # Rakuten slugs have no spaces or apostrophes
        return merchant.lower().replace(" ", "").replace("'", "")
    
    def _get_all_slugs(self, merchant: str) -> list:
        """Get all possible URL slugs to try for a merchant."""
        merchant_lower = merchant.lower().strip()
        slugs = []
        
        # Check for specific alternatives first
        if merchant_lower in self.SLUG_ALTERNATIVES:
            slugs.extend(self.SLUG_ALTERNATIVES[merchant_lower])
        
        # Add the primary slug
        primary_slug = self._get_slug(merchant)
        if primary_slug not in slugs:
            slugs.append(primary_slug)
        
        # Add fallback patterns
        basic_slug = merchant.lower().replace(" ", "").replace("'", "")
        if basic_slug not in slugs:
            slugs.append(basic_slug)
        
        # Add hyphenated version
        hyphen_slug = merchant.lower().replace(" ", "-").replace("'", "")
        if hyphen_slug not in slugs:
            slugs.append(hyphen_slug)
        
        return slugs
    
    def _is_not_found(self, body_text: str) -> bool:
        """Check if page is a 404 or vendor not available."""
        lower = body_text.lower()
        not_found_phrases = [
            "page not found",
            "doesn't exist",
            "does not exist",
            "we couldn't find",
            "we could not find",
            "404",
            "no longer available",
            "is not available",
            "store not found",
            "merchant not found",
            "this store is currently unavailable",
        ]
        return any(phrase in lower for phrase in not_found_phrases)
