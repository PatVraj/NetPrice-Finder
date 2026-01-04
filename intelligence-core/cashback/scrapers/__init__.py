"""
Cashback Platform Scrapers
Each platform has its own scraper module with custom logic for extracting rates and deals.
"""

from .base import BaseScraper, ScraperConfig
from .topcashback import TopCashbackScraper
from .rakuten import RakutenScraper
from .honey import HoneyScraper
from .befrugal import BeFrugalScraper
from .swagbucks import SwagbucksScraper

__all__ = [
    "BaseScraper",
    "ScraperConfig",
    "TopCashbackScraper",
    "RakutenScraper",
    "HoneyScraper",
    "BeFrugalScraper",
    "SwagbucksScraper",
]
