"""
Base Scraper Class for Cashback Platforms
Provides common functionality for all platform-specific scrapers.
"""

import os
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import httpx

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ScraperConfig:
    """Configuration for scraper behavior."""
    scraper_host: str = field(default_factory=lambda: os.getenv("SCRAPER_HOST", "http://scraper-engine:5000"))
    request_timeout: float = 30.0
    browser_timeout: float = 60.0
    max_retries: int = 2
    rate_limit_delay: float = 1.0  # Seconds between requests


@dataclass
class Deal:
    """A promotional deal from a cashback platform."""
    title: str
    cashback_rate: Optional[float] = None
    cashback_text: str = ""
    url: Optional[str] = None
    is_improved: bool = False
    category: Optional[str] = None


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


def is_merchant_match(search_term: str, found_name: str) -> bool:
    """Verify the found merchant actually matches what we're looking for."""
    search_lower = search_term.lower().strip()
    found_lower = found_name.lower().strip()
    
    # Exact match
    if search_lower == found_lower:
        return True
    
    # Search term is contained in found name
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


class BaseScraper(ABC):
    """
    Abstract base class for cashback platform scrapers.
    
    Each platform scraper should implement:
    - search(): Find cashback offers for a merchant
    - get_deals(): Get promotional deals (optional)
    """
    
    PLATFORM_NAME: str = "base"
    BASE_URL: str = ""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(f"cashback.scrapers.{self.PLATFORM_NAME}")
    
    @abstractmethod
    async def search(self, merchant: str, client: httpx.AsyncClient) -> list:
        """
        Search for cashback offers for a merchant.
        
        Args:
            merchant: Merchant name to search for
            client: HTTP client for making requests
            
        Returns:
            List of CashbackOffer objects
        """
        pass
    
    async def get_deals(self, merchant: str, client: httpx.AsyncClient) -> list[Deal]:
        """
        Get promotional deals for a merchant.
        
        Args:
            merchant: Merchant name
            client: HTTP client
            
        Returns:
            List of Deal objects
        """
        return []  # Default implementation returns empty list
    
    def make_slug(self, merchant: str) -> str:
        """Convert merchant name to URL slug."""
        return re.sub(r'[^a-z0-9]+', '-', merchant.lower().strip()).strip('-')
    
    def get_headers(self, extra: Optional[dict] = None) -> dict:
        """Get standard request headers."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        if extra:
            headers.update(extra)
        return headers
    
    async def _browser_extract(
        self, 
        client: httpx.AsyncClient, 
        url: str, 
        selectors: dict[str, list[str]],
        wait_for: str = "networkidle",
    ) -> Optional[dict]:
        """
        Use the scraper engine for browser-based extraction.
        
        Args:
            client: HTTP client
            url: URL to scrape
            selectors: Dict of {name: [css_selectors]} to extract
            wait_for: Wait strategy (networkidle, load, domcontentloaded)
            
        Returns:
            Extracted data dict or None on failure
        """
        try:
            response = await client.post(
                f"{self.config.scraper_host}/extract",
                json={
                    "url": url,
                    "selectors": selectors,
                    "wait_for": wait_for,
                    "timeout": 45000,
                },
                timeout=self.config.browser_timeout,
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.warning(f"Scraper engine returned {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.warning(f"Browser extract failed: {type(e).__name__}: {e}")
            return None
    
    def _filter_valid_rate(self, rate: float, max_rate: float = 25.0) -> bool:
        """
        Filter out obviously invalid rates.
        Cashback rates above 25% are usually errors or promo discounts.
        """
        return 0 < rate <= max_rate
