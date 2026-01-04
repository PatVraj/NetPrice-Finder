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
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Swagbucks for merchant rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        
        try:
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
                
                # Swagbucks shows "X SB per $" or "X% back"
                sb_pattern = r'(\d+)\s*SB\s*(?:per\s*\$|back)'
                percent_pattern = r'(\d+(?:\.\d+)?%)\s*back'
                
                sb_matches = re.findall(sb_pattern, html, re.IGNORECASE)
                percent_matches = re.findall(percent_pattern, html, re.IGNORECASE)
                
                percent = None
                cashback_text = None
                
                if percent_matches:
                    percent, _, original = parse_cashback_rate(percent_matches[0])
                    cashback_text = original
                elif sb_matches:
                    # SB = Swagbucks, roughly 1 SB = $0.01
                    sb_per_dollar = int(sb_matches[0])
                    percent = float(sb_per_dollar)  # Approximate as percentage
                    cashback_text = f"{sb_per_dollar} SB per $1"
                
                if percent and self._filter_valid_rate(percent):
                    logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {cashback_text}")
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
                    
        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Error: {e}")
        
        return offers
