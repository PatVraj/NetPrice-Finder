"""
Honey (PayPal Honey) Scraper
Extracts Honey Gold rewards and promo codes from JoinHoney.com
"""

import re
import logging
from datetime import datetime

import httpx

from .base import BaseScraper, parse_cashback_rate

logger = logging.getLogger(__name__)


class HoneyScraper(BaseScraper):
    """
    Scraper for Honey (PayPal Honey)
    
    Honey uses "Honey Gold" instead of direct cashback.
    Honey Gold can be redeemed for gift cards.
    
    NOTE: Temporarily disabled - joinhoney.com may be blocked or down.
    """
    
    PLATFORM_NAME = "honey"
    BASE_URL = "https://www.joinhoney.com"
    
    # Temporarily disable this scraper (site unreachable)
    ENABLED = False
    
    # Slug overrides for merchants with non-standard URLs
    SLUG_OVERRIDES = {
        "pandora": "pandora-jewelry",
        "pandora jewelry": "pandora-jewelry",
        "ulta": "ulta-beauty",
        "ulta beauty": "ulta-beauty",
        "macy's": "macys",
        "dick's sporting goods": "dicks-sporting-goods",
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Honey for merchant cashback/rewards."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        # Skip if disabled
        if not self.ENABLED:
            logger.debug(f"[Honey] Scraper disabled - skipping {merchant}")
            return []
        
        offers = []
        
        try:
            # Strategy 1: Try known slug overrides
            slugs_to_try = self._get_all_slugs(merchant)
            
            for slug in slugs_to_try:
                url = f"{self.BASE_URL}/shop/{slug}"
                logger.debug(f"[Honey] Trying URL: {url}")
                
                response = await client.get(
                    url,
                    headers=self.get_headers(),
                    follow_redirects=True,
                    timeout=10.0,
                )
                
                if response.status_code == 200 and not self._is_not_found(response.text):
                    html = response.text
                    
                    # Look for Honey Gold rewards
                    gold_pattern = r'(\d+(?:\.\d+)?)\s*%?\s*(?:Honey\s*Gold|Gold\s*rewards?|back|Cash\s*Back)'
                    matches = re.findall(gold_pattern, html, re.IGNORECASE)
                    
                    if matches:
                        rate_text = matches[0]
                        try:
                            percent = float(rate_text)
                        except ValueError:
                            percent, _, _ = parse_cashback_rate(rate_text)
                        
                        if percent and self._filter_valid_rate(percent):
                            logger.info(f"[Honey] ✓ Found {merchant}: {percent}% Honey Gold")
                            offers.append(CashbackOffer(
                                platform=CashbackPlatform.HONEY,
                                merchant=merchant,
                                cashback_percent=percent,
                                cashback_text=f"{percent}% Honey Gold",
                                affiliate_url=url,
                                terms="Honey Gold can be redeemed for gift cards",
                                last_updated=datetime.now().isoformat(),
                                confidence=0.8,
                            ))
                            return offers
                            
        except Exception as e:
            logger.debug(f"[Honey] Error: {e}")
        
        logger.debug(f"[Honey] No offers found for '{merchant}'")
        return offers
    
    def _get_all_slugs(self, merchant: str) -> list:
        """Get all possible URL slugs to try for a merchant."""
        merchant_lower = merchant.lower()
        slugs = []
        
        # Check for override first
        if merchant_lower in self.SLUG_OVERRIDES:
            slugs.append(self.SLUG_OVERRIDES[merchant_lower])
        
        # Standard slug
        standard_slug = self.make_slug(merchant)
        if standard_slug not in slugs:
            slugs.append(standard_slug)
        
        return slugs
    
    def _is_not_found(self, html: str) -> bool:
        """Check if the page indicates merchant not found."""
        not_found_phrases = [
            "store not found",
            "page not found",
            "no results",
            "doesn't have any",
            "not available",
        ]
        html_lower = html.lower()
        return any(phrase in html_lower for phrase in not_found_phrases)
