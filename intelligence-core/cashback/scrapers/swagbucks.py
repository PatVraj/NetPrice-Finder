"""
Swagbucks Scraper
Extracts cashback rates from Swagbucks Shop
"""

import re
import logging
from urllib.parse import quote_plus
from datetime import datetime

import httpx

from .base import BaseScraper, parse_cashback_rate

logger = logging.getLogger(__name__)


class SwagbucksScraper(BaseScraper):
    """
    Scraper for Swagbucks Shop
    
    Swagbucks uses SB (Swagbucks) as currency, where ~100 SB = $1.
    They also show percentage-based cashback.
    """
    
    PLATFORM_NAME = "swagbucks"
    BASE_URL = "https://www.swagbucks.com"
    SEARCH_URL = "https://www.swagbucks.com/shop/search"
    
    # Slug overrides for merchants with non-standard URLs
    SLUG_OVERRIDES = {
        "pandora": "pandora-jewelry",
        "pandora jewelry": "pandora-jewelry",
        "ulta": "ulta-beauty", 
        "ulta beauty": "ulta-beauty",
    }
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Swagbucks for merchant rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
            # Strategy 1: Search page
            logger.debug(f"[Swagbucks] Strategy 1: Search page for '{merchant}'")
            params = {"q": merchant}
            
            response = await client.get(
                self.SEARCH_URL,
                params=params,
                headers=self.get_headers(),
                follow_redirects=True,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                html = response.text
                
                # Check for no results
                if self._is_not_found(html):
                    logger.debug(f"[Swagbucks] No search results for '{merchant}'")
                    return offers
                
                merchant_lower = merchant.lower()
                
                # Swagbucks shows "X SB per $" or "X% back"
                # Look for merchant name followed by rate
                patterns = [
                    # "Nike 8% Cash Back"
                    rf'({re.escape(merchant)})[^<]*?(\d+(?:\.\d+)?)\s*%\s*(?:Cash\s*Back|back)',
                    # "Nike 8 SB per $"
                    rf'({re.escape(merchant)})[^<]*?(\d+)\s*SB\s*(?:per\s*\$|back)',
                    # Just rate near merchant name
                    rf'({re.escape(merchant)})[^<]*?(\d+(?:\.\d+)?)\s*%',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        rate_str = match.group(2)
                        percent = float(rate_str)
                        
                        # Determine cashback text
                        if "sb" in match.group(0).lower():
                            cashback_text = f"{int(percent)} SB per $1"
                        else:
                            cashback_text = f"{percent}% Cash Back"
                        
                        if self._filter_valid_rate(percent):
                            logger.info(f"[Swagbucks] ✓ Found {merchant}: {cashback_text}")
                            offers.append(CashbackOffer(
                                platform=CashbackPlatform.SWAGBUCKS,
                                merchant=merchant,
                                cashback_percent=percent,
                                cashback_text=cashback_text,
                                terms="Earn Swagbucks (SB) redeemable for gift cards",
                                affiliate_url=f"{self.SEARCH_URL}?q={quote_plus(merchant)}",
                                last_updated=datetime.now().isoformat(),
                                confidence=0.8,
                            ))
                            return offers
                    
        except Exception as e:
            logger.debug(f"[Swagbucks] Error: {e}")
        
        logger.debug(f"[Swagbucks] No offers found for '{merchant}'")
        return offers
    
    def _is_not_found(self, html: str) -> bool:
        """Check if the page indicates no results found."""
        not_found_phrases = [
            "no results",
            "0 results",
            "nothing found",
            "no stores found",
            "try a different search",
        ]
        html_lower = html.lower()
        return any(phrase in html_lower for phrase in not_found_phrases)
