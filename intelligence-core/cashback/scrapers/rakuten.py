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
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Rakuten for a merchant."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
            # Try the API first (faster and more reliable)
            api_offers = await self._search_api(merchant, client)
            if api_offers:
                return api_offers
            
            # Fall back to browser scraping
            browser_offers = await self._scrape_merchant_page(merchant, client)
            if browser_offers:
                return browser_offers
                
        except Exception as e:
            logger.warning(f"[{self.PLATFORM_NAME}] Error: {type(e).__name__}: {e}")
        
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
        slug = self._get_slug(merchant)
        merchant_url = f"https://www.rakuten.com/shop/{slug}"
        
        logger.debug(f"[{self.PLATFORM_NAME}] Browser scraping: {merchant_url}")
        
        data = await self._browser_extract(
            client,
            merchant_url,
            {},  # No specific selectors needed
            wait_for="networkidle",
        )
        
        if not data:
            return offers
        
        body_text = data.get("body_text", "")
        
        logger.debug(f"[{self.PLATFORM_NAME}] Got body_text: {len(body_text)} chars")
        
        # Check for 404 page
        if self._is_not_found(body_text):
            logger.debug(f"[{self.PLATFORM_NAME}] Page not found for '{merchant}'")
            return offers
        
        # Parse body_text for cashback rates
        patterns = [
            # "Get 6% Cash Back" pattern
            r'Get\s+(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "X% Cash Back" pattern
            r'(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            # "Up to X%" pattern
            r'Up\s+to\s+(\d+(?:\.\d+)?)\s*%',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                percent = float(match.group(1))
                # Filter valid rates (cashback rarely exceeds 25%)
                if self._filter_valid_rate(percent):
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back")
                    offers.append(CashbackOffer(
                        platform=CashbackPlatform.RAKUTEN,
                        merchant=merchant,
                        cashback_percent=percent,
                        cashback_fixed=None,
                        cashback_text=f"{percent}% Cash Back",
                        affiliate_url=merchant_url,
                        last_updated=datetime.now().isoformat(),
                        confidence=0.9,
                    ))
                    break
        
        if not offers:
            logger.debug(f"[{self.PLATFORM_NAME}] No rate pattern matched for '{merchant}'")
        
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
        """Get URL slug for merchant."""
        merchant_lower = merchant.lower().strip()
        if merchant_lower in self.SLUG_OVERRIDES:
            return self.SLUG_OVERRIDES[merchant_lower]
        # Rakuten slugs have no spaces or apostrophes
        return merchant.lower().replace(" ", "").replace("'", "")
    
    def _is_not_found(self, body_text: str) -> bool:
        """Check if page is a 404."""
        lower = body_text.lower()
        return any(phrase in lower for phrase in [
            "page not found",
            "doesn't exist",
            "we couldn't find",
            "404",
        ])
