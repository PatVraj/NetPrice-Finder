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
    """
    
    PLATFORM_NAME = "honey"
    BASE_URL = "https://www.joinhoney.com"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search Honey for merchant cashback/rewards."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        slug = self.make_slug(merchant)
        url = f"{self.BASE_URL}/shop/{slug}"
        
        try:
            response = await client.get(
                url,
                headers=self.get_headers(),
                follow_redirects=True,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                html = response.text
                
                # Look for Honey Gold rewards
                gold_pattern = r'(\d+(?:\.\d+)?%?)\s*(?:Honey\s*Gold|Gold\s*rewards?|back)'
                matches = re.findall(gold_pattern, html, re.IGNORECASE)
                
                if matches:
                    rate_text = matches[0]
                    percent, fixed, original = parse_cashback_rate(rate_text)
                    
                    if percent and self._filter_valid_rate(percent):
                        logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Honey Gold")
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
                        
        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Error: {e}")
        
        return offers
    
    async def get_promo_codes(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Get promo codes from Honey for a merchant."""
        from ..monitor import PromoCode, CashbackPlatform
        
        promos = []
        slug = self.make_slug(merchant)
        url = f"{self.BASE_URL}/shop/{slug}"
        
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
            r'"code"\s*:\s*"([A-Z0-9]+)"',
            r'data-coupon-code="([A-Z0-9]+)"',
            r'class="[^"]*coupon[^"]*"[^>]*>([A-Z0-9]{4,20})<',
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for code in matches[:5]:
                code_upper = code.upper()
                if code_upper not in seen_codes and len(code_upper) >= 4:
                    seen_codes.add(code_upper)
                    
                    # Try to find success rate
                    success_match = re.search(
                        rf'{code}[^<]*?(\d+)%\s*success',
                        html, re.IGNORECASE
                    )
                    success_rate = float(success_match.group(1)) if success_match else None
                    
                    promos.append(PromoCode(
                        platform=CashbackPlatform.HONEY,
                        merchant=merchant,
                        code=code_upper,
                        description=f"Honey verified code for {merchant}",
                        success_rate=success_rate,
                        affiliate_url=url,
                    ))
        
        return promos
