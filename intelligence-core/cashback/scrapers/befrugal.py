"""
BeFrugal Scraper
Extracts cashback rates from BeFrugal.com
"""

import re
import logging
from datetime import datetime

import httpx

from .base import BaseScraper, parse_cashback_rate

logger = logging.getLogger(__name__)


class BeFrugalScraper(BaseScraper):
    """
    Scraper for BeFrugal.com
    
    BeFrugal offers direct cashback that can be withdrawn as PayPal or check.
    URL pattern: https://www.befrugal.com/store/{merchant}/
    """
    
    PLATFORM_NAME = "befrugal"
    BASE_URL = "https://www.befrugal.com"
    
    # Slug overrides for merchants with non-standard URLs
    SLUG_OVERRIDES = {
        "pandora": "pandora",
        "pandora jewelry": "pandora",
        "ulta": "ulta",
        "ulta beauty": "ulta",
        "macy's": "macys",
        "dick's sporting goods": "dicks-sporting-goods",
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search BeFrugal for merchant rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
            # BeFrugal uses /store/{merchant}/ URL pattern
            slugs_to_try = self._get_all_slugs(merchant)
            
            for slug in slugs_to_try:
                url = f"{self.BASE_URL}/store/{slug}/"
                logger.debug(f"[BeFrugal] Trying URL: {url}")
                
                response = await client.get(
                    url,
                    headers=self.get_headers(),
                    follow_redirects=True,
                    timeout=10.0,
                )
                
                if response.status_code == 200:
                    html = response.text
                    
                    # Check if page says no cashback available
                    if self._is_no_cashback(html):
                        logger.debug(f"[BeFrugal] Vendor exists but no cashback for '{merchant}'")
                        return offers
                    
                    # Check if 404/not found
                    if self._is_not_found(html):
                        continue
                    
                    # BeFrugal shows cashback prominently
                    rate_pattern = r'(\d+(?:\.\d+)?)\s*%\s*(?:Cash\s*Back|cashback)'
                    matches = re.findall(rate_pattern, html, re.IGNORECASE)
                    
                    if matches:
                        percent = float(matches[0])
                        
                        if self._filter_valid_rate(percent):
                            logger.info(f"[BeFrugal] ✓ Found {merchant}: {percent}% Cash Back")
                            offers.append(CashbackOffer(
                                platform=CashbackPlatform.BEFRUGAL,
                                merchant=merchant,
                                cashback_percent=percent,
                                cashback_text=f"{percent}% Cash Back",
                                affiliate_url=url,
                                last_updated=datetime.now().isoformat(),
                                confidence=0.85,
                            ))
                            return offers
                        
        except Exception as e:
            logger.debug(f"[BeFrugal] Error: {e}")
        
        logger.debug(f"[BeFrugal] No offers found for '{merchant}'")
        return offers
    
    def _is_no_cashback(self, html: str) -> bool:
        """Check if page says cashback is not available for this vendor."""
        no_cashback_phrases = [
            "cash back is currently not available",
            "cashback is currently not available",
            "no cash back available",
            "not currently offering cash back",
        ]
        html_lower = html.lower()
        return any(phrase in html_lower for phrase in no_cashback_phrases)
    
    def _get_all_slugs(self, merchant: str) -> list:
        """Get all possible URL slugs to try for a merchant."""
        merchant_lower = merchant.lower()
        slugs = []
        
        # Check for override first
        if merchant_lower in self.SLUG_OVERRIDES:
            slugs.append(self.SLUG_OVERRIDES[merchant_lower])
        
        # Standard slug
        standard_slug = merchant.lower().replace(" ", "-")
        if standard_slug not in slugs:
            slugs.append(standard_slug)
        
        return slugs
    
    def _is_not_found(self, html: str) -> bool:
        """Check if the page indicates merchant not found."""
        not_found_phrases = [
            "store not found",
            "page not found",
            "no results",
            "not available",
            "couldn't find",
        ]
        html_lower = html.lower()
        return any(phrase in html_lower for phrase in not_found_phrases)
