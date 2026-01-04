"""
TopCashback Scraper
Extracts cashback rates, deals, and promo codes from TopCashback.com
"""

import re
import json
import logging
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field

import httpx

from .base import (
    BaseScraper, 
    ScraperConfig, 
    Deal,
    parse_cashback_rate, 
    is_merchant_match,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TopCashback Page Structure
# =============================================================================
# 
# Key CSS Selectors:
# 
# Main Rate Card (.merch-rate-card):
#   - .merch-cat__title: Merchant name (e.g., "Nike Cash Back")
#   - .merch-cat__sub-cat: Category (e.g., "Online Purchase")
#   - .merch-cat__tag: Tag like "Improved"
#   - .merch-cat__rate: The rate (e.g., "8%")
#
# Logged-out Header:
#   - .merch-logged-out-text__header: "Get 8% of the price back..."
#
# Deals Section (.merch-offers-wrap):
#   - .merch-filters__amount-available: Number of deals (e.g., "8")
#   - .merch-offer: Individual deal card
#   - .merch-offer__title: Deal description
#   - .merch-offer__rate: Rate for this deal (e.g., "8% Cash Back")
#
# =============================================================================


@dataclass
class TopCashbackDeal:
    """A promotional deal from TopCashback."""
    title: str
    cashback_percent: Optional[float] = None
    cashback_text: str = ""
    url: Optional[str] = None
    is_improved: bool = False


class TopCashbackScraper(BaseScraper):
    """
    Scraper for TopCashback.com
    
    Extracts:
    - Main cashback rate from the rate card
    - Individual deals with their rates
    - Promo codes when available
    """
    
    PLATFORM_NAME = "topcashback"
    BASE_URL = "https://www.topcashback.com"
    SEARCH_API = "https://www.topcashback.com/ajax/merchant/search"
    
    # CSS Selectors for extraction
    SELECTORS = {
        # Main rate elements
        "cashback_header": [".merch-logged-out-text__header", "h2.merch-logged-out-text__header"],
        "rate_card_rate": [".merch-cat__rate", ".merch-rate-card .merch-cat__rate"],
        "rate_card_title": [".merch-cat__title", ".merch-rate-card .merch-cat__title"],
        "rate_card_category": [".merch-cat__sub-cat"],
        "rate_card_tag": [".merch-cat__tag span"],
        
        # Deals section
        "deals_count": [".merch-filters__amount-available"],
    }
    
    # Slug overrides for merchants with non-standard URLs
    SLUG_OVERRIDES = {
        "nike": "nike",
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
        "adidas": "adidas",
        "pandora": "pandora-jewelry",
        "pandora jewelry": "pandora-jewelry",
        "ulta": "ulta-beauty",
        "ulta beauty": "ulta-beauty",
        "kohl's": "kohls",
        "kohls": "kohls",
        "kendra scott": "kendra-scott",
        "kay jewelers": "kay-jewelers",
        "zales": "zales",
        "swarovski": "swarovski",
    }
    
    # Alternative slugs to try if the primary doesn't work
    SLUG_ALTERNATIVES = {
        "pandora": ["pandora-jewelry", "pandora"],
        "ulta": ["ulta-beauty", "ulta"],
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search TopCashback for merchant cashback rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
            # Strategy 1: Search page (most reliable)
            search_offers = await self._search_page(merchant, client)
            if search_offers:
                return search_offers
            
            # Strategy 2: Try API (may be limited)
            api_offers = await self._search_api(merchant, client)
            if api_offers:
                return api_offers
            
            # Strategy 3: Fall back to direct merchant page
            browser_offers = await self._scrape_merchant_page(merchant, client)
            if browser_offers:
                return browser_offers
                
        except Exception as e:
            logger.warning(f"[{self.PLATFORM_NAME}] Error: {type(e).__name__}: {e}")
        
        return offers
    
    async def _search_page(self, merchant: str, client: httpx.AsyncClient) -> list:
        """
        Scrape the TopCashback search results page.
        
        URL format: https://www.topcashback.com/search/merchants/?s=nike
        Returns results like: "Nike Improved Offer 8% Cash Back"
        """
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        search_url = f"{self.BASE_URL}/search/merchants/?s={merchant}"
        
        logger.debug(f"[{self.PLATFORM_NAME}] Searching via page: {search_url}")
        
        data = await self._browser_extract(
            client,
            search_url,
            {},  # No specific selectors - parse body_text
            wait_for="networkidle",
        )
        
        if not data:
            logger.debug(f"[{self.PLATFORM_NAME}] Search page returned no data")
            return offers
        
        body_text = data.get("body_text", "")
        
        logger.debug(f"[{self.PLATFORM_NAME}] Search page body: {len(body_text)} chars")
        
        # Check if we found results
        if "we found 0 results" in body_text.lower():
            logger.debug(f"[{self.PLATFORM_NAME}] No search results for '{merchant}'")
            return offers
        
        merchant_lower = merchant.lower()
        
        # Pattern: "Nike Improved Offer 8% Cash Back" or "Nike 8% Cash Back"
        # Also handles "Up to X% Cash Back"
        patterns = [
            # "Nike Improved Offer 8% Cash Back" - with improved tag
            rf'({re.escape(merchant)})\s*Improved\s*(?:Offer\s*)?(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "Nike 8% Cash Back" - standard format
            rf'({re.escape(merchant)})\s*(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "Nike Up to 8% Cash Back"
            rf'({re.escape(merchant)})\s*Up\s+to\s+(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                percent = float(match.group(2))
                if self._filter_valid_rate(percent):
                    is_improved = "improved" in match.group(0).lower()
                    
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (search page){' (improved)' if is_improved else ''}")
                    
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_fixed=None,
                        cashback_text=f"{percent}% Cash Back",
                        affiliate_url=f"{self.BASE_URL}/{self._get_slug(merchant)}/",
                        last_updated=datetime.now().isoformat(),
                        is_elevated=is_improved,
                        confidence=0.95,
                    ))
                    return offers
        
        # NO FALLBACK - if the exact merchant name isn't found with a rate, 
        # they don't have this merchant. Don't grab rates from other stores!
        logger.debug(f"[{self.PLATFORM_NAME}] Merchant '{merchant}' not found in search results (no exact match)")
        return offers
    
    async def _search_api(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Try the TopCashback search API."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.topcashback.com/",
        }
        
        try:
            response = await client.get(
                self.SEARCH_API,
                params={"term": merchant, "maxResults": 5},
                headers=headers,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                merchants = data if isinstance(data, list) else data.get("merchants", [])
                
                for m in merchants:
                    name = m.get("name", m.get("merchantName", ""))
                    if is_merchant_match(merchant, name):
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
                                    confidence=0.95,
                                ))
                                return offers
                                
            elif response.status_code != 404:
                logger.warning(f"[{self.PLATFORM_NAME}] API returned {response.status_code}")
                
        except (json.JSONDecodeError, httpx.RequestError) as e:
            logger.debug(f"[{self.PLATFORM_NAME}] API failed: {e}")
        
        return offers
    
    async def _scrape_merchant_page(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Scrape merchant page using browser engine."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        merchant_lower = merchant.lower().strip()
        
        # Get all slugs to try
        slugs_to_try = self._get_all_slugs(merchant)
        
        data = None
        successful_url = None
        
        # Try each slug
        for slug in slugs_to_try:
            merchant_url = f"{self.BASE_URL}/{slug}/"
            logger.debug(f"[{self.PLATFORM_NAME}] Trying: {merchant_url}")
            
            data = await self._browser_extract(
                client,
                merchant_url,
                self.SELECTORS,
                wait_for="networkidle",
            )
            
            if data:
                body_text = data.get("body_text", "")
                # Check if this is NOT a 404 page and has meaningful content
                if not self._is_not_found(body_text) and len(body_text) > 200:
                    successful_url = merchant_url
                    logger.debug(f"[{self.PLATFORM_NAME}] Found valid page at {merchant_url}")
                    break
        
        if not data or not successful_url:
            logger.debug(f"[{self.PLATFORM_NAME}] No valid page found for '{merchant}' (vendor not available)")
            return offers
        
        body_text = data.get("body_text", "")
        html = data.get("html", "")
        extracted = data.get("extracted", {})
        merchant_url = successful_url  # Use the successful URL from here on
        
        # Strategy 1: Extract from rate card (.merch-cat__rate)
        rate_card_rate = extracted.get("rate_card_rate", "")
        if rate_card_rate:
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', rate_card_rate)
            if match:
                percent = float(match.group(1))
                if self._filter_valid_rate(percent):
                    is_improved = "improved" in extracted.get("rate_card_tag", "").lower()
                    category = extracted.get("rate_card_category", "Online Purchase")
                    
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (rate card)")
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_text=f"{percent}% Cash Back",
                        category=category,
                        is_elevated=is_improved,
                        affiliate_url=merchant_url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.98,  # Very high - direct from rate card
                    ))
                    return offers
        
        # Strategy 2: Extract from logged-out header
        cashback_header = extracted.get("cashback_header", "")
        if cashback_header:
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', cashback_header)
            if match:
                percent = float(match.group(1))
                if self._filter_valid_rate(percent):
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (header)")
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_text=f"{percent}% Cash Back",
                        affiliate_url=merchant_url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.95,
                    ))
                    return offers
        
        # Strategy 3: Parse body_text for rate patterns
        offer = self._parse_body_text(merchant, body_text, merchant_url)
        if offer:
            offers.append(offer)
            return offers
        
        # Strategy 4: Parse HTML for rate patterns
        offer = self._parse_html_rates(merchant, html, merchant_url)
        if offer:
            offers.append(offer)
        
        return offers
    
    def _parse_body_text(self, merchant: str, body_text: str, url: str):
        """Parse body text for cashback rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        patterns = [
            # Rate card format "8%"
            r'(?:^|\s)(\d+(?:\.\d+)?)\s*%\s*$',
            # "Get 8% of the price back"
            r'Get\s+(\d+(?:\.\d+)?)\s*%\s+of\s+the\s+price',
            # "X% Cash Back"
            r'(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "Up to X%"
            r'Up\s+to\s+(\d+(?:\.\d+)?)\s*%',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE | re.MULTILINE)
            if match:
                percent = float(match.group(1))
                if self._filter_valid_rate(percent):
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back (body)")
                    return CashbackOffer(
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_text=f"{percent}% Cash Back",
                        affiliate_url=url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.9,
                    )
        
        return None
    
    def _parse_html_rates(self, merchant: str, html: str, url: str):
        """Parse HTML for rate elements."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        # Look for rate in merch-cat__rate class
        rate_match = re.search(
            r'class="[^"]*merch-cat__rate[^"]*"[^>]*>\s*(\d+(?:\.\d+)?)\s*%',
            html, re.IGNORECASE
        )
        if rate_match:
            percent = float(rate_match.group(1))
            if self._filter_valid_rate(percent):
                logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% (HTML)")
                return CashbackOffer(
                    platform=CashbackPlatform.TOPCASHBACK,
                    merchant=merchant,
                    cashback_percent=percent,
                    cashback_text=f"{percent}% Cash Back",
                    affiliate_url=url,
                    last_updated=datetime.now().isoformat(),
                    confidence=0.85,
                )
        
        return None
    
    async def get_deals(self, merchant: str, client: httpx.AsyncClient) -> list[TopCashbackDeal]:
        """
        Get promotional deals from TopCashback.
        
        These are the "Nike promotions" section with deals like:
        - "Shop Men's Shoes $100 and Under"
        - "Activewear Styles Up to 40% off!"
        """
        deals = []
        slug = self._get_slug(merchant)
        merchant_url = f"{self.BASE_URL}/{slug}/"
        
        # We need HTML for this - use body_text to parse deals
        data = await self._browser_extract(
            client,
            merchant_url,
            {
                "deals_section": [".merch-offers", "#deals"],
            },
            wait_for="networkidle",
        )
        
        if not data:
            return deals
        
        body_text = data.get("body_text", "")
        html = data.get("html", "")
        
        # Parse deal cards from HTML
        # Pattern: <p class="merch-offer__title">TITLE</p>...<span class="merch-offer__rate">RATE</span>
        deal_pattern = re.compile(
            r'class="merch-offer__title"[^>]*>([^<]+)</p>.*?'
            r'class="merch-offer__rate"[^>]*>([^<]+)</span>',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in deal_pattern.finditer(html):
            title = match.group(1).strip()
            rate_text = match.group(2).strip()
            
            # Parse the rate
            rate_match = re.search(r'(\d+(?:\.\d+)?)\s*%', rate_text)
            percent = float(rate_match.group(1)) if rate_match else None
            
            if title and percent:
                deals.append(TopCashbackDeal(
                    title=title,
                    cashback_percent=percent,
                    cashback_text=rate_text,
                    url=merchant_url,
                ))
        
        return deals
    
    async def get_promo_codes(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Get promo codes from TopCashback."""
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
            r'class="[^"]*code[^"]*"[^>]*>([A-Z0-9]{4,20})<',
            r'"couponCode"\s*:\s*"([A-Z0-9]+)"',
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for code in matches[:5]:
                code_upper = code.upper()
                if code_upper not in seen_codes and len(code_upper) >= 4:
                    seen_codes.add(code_upper)
                    
                    # Try to extract discount info
                    desc_match = re.search(
                        rf'{code}[^<]*?(\d+%\s*off|\$\d+\s*off|free\s*shipping)',
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
                        platform=CashbackPlatform.TOPCASHBACK,
                        merchant=merchant,
                        code=code_upper,
                        description=description or f"TopCashback code for {merchant}",
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
        return self.make_slug(merchant)
    
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
        
        # Add hyphenated version (TopCashback prefers hyphens)
        hyphen_slug = merchant.lower().replace(" ", "-").replace("'", "")
        if hyphen_slug not in slugs:
            slugs.append(hyphen_slug)
        
        # Add no-space version
        nospace_slug = merchant.lower().replace(" ", "").replace("'", "")
        if nospace_slug not in slugs:
            slugs.append(nospace_slug)
        
        return slugs
    
    def _is_not_found(self, body_text: str) -> bool:
        """Check if page is a 404 or vendor not available."""
        lower = body_text.lower()
        not_found_phrases = [
            "page not found",
            "page you requested",
            "sorry, the page",
            "we couldn't find",
            "we could not find",
            "does not exist",
            "doesn't exist",
            "404",
            "no longer available",
            "is not available",
            "merchant not found",
            "store not found",
            "this merchant is currently unavailable",
            "we found 0 results",  # Search page with no results
        ]
        return any(phrase in lower for phrase in not_found_phrases)
