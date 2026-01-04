"""
BeFrugal Scraper
Extracts cashback rates and promo codes from BeFrugal.com
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
    """
    
    PLATFORM_NAME = "befrugal"
    BASE_URL = "https://www.befrugal.com"
    
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Search BeFrugal for merchant rates."""
        from ..monitor import CashbackOffer, CashbackPlatform
        
        offers = []
        slug = merchant.lower().replace(" ", "-")
        url = f"{self.BASE_URL}/coupons/{slug}"
        
        try:
            response = await client.get(
                url,
                headers=self.get_headers(),
                follow_redirects=True,
                timeout=10.0,
            )
            
            if response.status_code == 200:
                html = response.text
                
                # BeFrugal shows cashback prominently
                rate_pattern = r'(\d+(?:\.\d+)?%)\s*(?:Cash\s*Back|cashback)'
                matches = re.findall(rate_pattern, html, re.IGNORECASE)
                
                if matches:
                    percent, fixed, original = parse_cashback_rate(matches[0])
                    
                    if percent and self._filter_valid_rate(percent):
                        logger.info(f"[{self.PLATFORM_NAME}] ✓ Found {merchant}: {percent}% Cash Back")
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
                        
        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Error: {e}")
        
        return offers
    
    async def get_promo_codes(self, merchant: str, client: httpx.AsyncClient) -> list:
        """Get promo codes from BeFrugal for a merchant."""
        from ..monitor import PromoCode, CashbackPlatform
        
        promos = []
        slug = merchant.lower().replace(" ", "-")
        url = f"{self.BASE_URL}/coupons/{slug}"
        
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
            r'data-coupon-code="([A-Z0-9]+)"',
            r'class="[^"]*coupon[^"]*code[^"]*"[^>]*>([A-Z0-9]{4,20})<',
            r'"code"\s*:\s*"([A-Z0-9]+)"',
        ]
        
        for pattern in code_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for code in matches[:5]:
                code_upper = code.upper()
                if code_upper not in seen_codes and len(code_upper) >= 4:
                    seen_codes.add(code_upper)
                    promos.append(PromoCode(
                        platform=CashbackPlatform.BEFRUGAL,
                        merchant=merchant,
                        code=code_upper,
                        description=f"BeFrugal code for {merchant}",
                        affiliate_url=url,
                    ))
        
        return promos
