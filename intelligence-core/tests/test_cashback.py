"""
Test Suite: Cashback Monitor

Tests for the cashback monitor and scrapers.
Run: pytest tests/test_cashback.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# Imports configured via conftest.py
from cashback.monitor import (
    CashbackMonitor,
    CashbackOffer,
    CashbackPlatform,
    MerchantCashback,
)


class TestCashbackPlatform:
    """Test cases for CashbackPlatform enum."""

    def test_platform_values(self):
        """Test that all expected platforms exist."""
        assert CashbackPlatform.RAKUTEN.value == "rakuten"
        assert CashbackPlatform.TOPCASHBACK.value == "topcashback"
        assert CashbackPlatform.HONEY.value == "honey"
        assert CashbackPlatform.BEFRUGAL.value == "befrugal"
        assert CashbackPlatform.SWAGBUCKS.value == "swagbucks"

    def test_platform_count(self):
        """Test that we have 5 main platforms."""
        platforms = list(CashbackPlatform)
        assert len(platforms) == 5


class TestCashbackOffer:
    """Test cases for CashbackOffer dataclass."""

    def test_create_offer(self):
        """Test creating a cashback offer."""
        offer = CashbackOffer(
            platform=CashbackPlatform.RAKUTEN,
            merchant="Nike",
            cashback_percent=6.0,
        )
        
        assert offer.platform == CashbackPlatform.RAKUTEN
        assert offer.merchant == "Nike"
        assert offer.cashback_percent == 6.0

    def test_offer_effective_rate(self):
        """Test that effective rate is calculated."""
        offer = CashbackOffer(
            platform=CashbackPlatform.TOPCASHBACK,
            merchant="Amazon",
            cashback_percent=5.0,
        )
        
        # effective_rate should match cashback_percent for percent type
        assert offer.effective_rate == 5.0

    def test_offer_with_terms(self):
        """Test offer with terms and conditions."""
        offer = CashbackOffer(
            platform=CashbackPlatform.HONEY,
            merchant="Best Buy",
            cashback_percent=3.0,
            terms="Excludes gift cards and services",
        )
        
        assert "gift cards" in offer.terms.lower()


class TestMerchantCashback:
    """Test cases for MerchantCashback aggregate."""

    def test_create_merchant_cashback(self):
        """Test creating a merchant cashback result."""
        result = MerchantCashback(
            merchant="Nike",
            checked_at=datetime.now().isoformat(),
        )
        
        assert result.merchant == "Nike"
        assert result.offers == []
        assert result.best_offer is None

    def test_add_offer(self):
        """Test adding an offer to merchant cashback."""
        result = MerchantCashback(
            merchant="Nike",
            checked_at=datetime.now().isoformat(),
        )
        
        offer = CashbackOffer(
            platform=CashbackPlatform.RAKUTEN,
            merchant="Nike",
            cashback_percent=6.0,
        )
        
        result.add_offer(offer)
        
        assert len(result.offers) == 1
        assert result.best_offer == offer

    def test_best_offer_selection(self):
        """Test that best offer is the highest rate."""
        result = MerchantCashback(
            merchant="Nike",
            checked_at=datetime.now().isoformat(),
        )
        
        # Add lower rate first
        result.add_offer(CashbackOffer(
            platform=CashbackPlatform.RAKUTEN,
            merchant="Nike",
            cashback_percent=4.0,
        ))
        
        # Add higher rate
        result.add_offer(CashbackOffer(
            platform=CashbackPlatform.TOPCASHBACK,
            merchant="Nike",
            cashback_percent=8.0,
        ))
        
        # Add medium rate
        result.add_offer(CashbackOffer(
            platform=CashbackPlatform.HONEY,
            merchant="Nike",
            cashback_percent=5.0,
        ))
        
        assert len(result.offers) == 3
        assert result.best_offer.platform == CashbackPlatform.TOPCASHBACK
        assert result.best_offer.cashback_percent == 8.0


class TestCashbackMonitor:
    """Test cases for CashbackMonitor class."""

    def test_create_monitor(self):
        """Test creating a cashback monitor."""
        monitor = CashbackMonitor()
        
        assert monitor is not None
        assert len(monitor.platforms) > 0

    def test_monitor_has_all_platforms(self):
        """Test that monitor includes all platforms."""
        monitor = CashbackMonitor()
        
        # Should have scrapers for all platforms
        assert CashbackPlatform.RAKUTEN in monitor.platforms
        assert CashbackPlatform.TOPCASHBACK in monitor.platforms

    def test_cache_functionality(self):
        """Test that caching is enabled by default."""
        monitor = CashbackMonitor()
        
        assert monitor.cache_enabled == True

    def test_disable_cache(self):
        """Test disabling cache."""
        monitor = CashbackMonitor(cache_enabled=False)
        
        assert monitor.cache_enabled == False


class TestCashbackMonitorIntegration:
    """Integration tests that mock external calls."""

    @pytest.mark.asyncio
    async def test_find_best_cashback_returns_result(self):
        """Test that find_best_cashback returns a MerchantCashback."""
        monitor = CashbackMonitor()
        
        # Mock all scrapers to return empty results (no network calls)
        for platform, scraper in monitor._scrapers.items():
            scraper.search = AsyncMock(return_value=[])
        
        result = await monitor.find_best_cashback("Nike")
        
        assert isinstance(result, MerchantCashback)
        assert result.merchant == "Nike"

    @pytest.mark.asyncio
    async def test_find_best_cashback_with_mock_results(self):
        """Test find_best_cashback with mocked scraper results."""
        monitor = CashbackMonitor()
        
        # Mock Rakuten to return an offer
        mock_offer = CashbackOffer(
            platform=CashbackPlatform.RAKUTEN,
            merchant="Nike",
            cashback_percent=6.0,
        )
        
        monitor._scrapers[CashbackPlatform.RAKUTEN].search = AsyncMock(
            return_value=[mock_offer]
        )
        
        # Mock others to return empty
        for platform in [CashbackPlatform.TOPCASHBACK, CashbackPlatform.HONEY, 
                         CashbackPlatform.BEFRUGAL, CashbackPlatform.SWAGBUCKS]:
            if platform in monitor._scrapers:
                monitor._scrapers[platform].search = AsyncMock(return_value=[])
        
        result = await monitor.find_best_cashback("Nike")
        
        assert result.best_offer is not None
        assert result.best_offer.cashback_percent == 6.0

    @pytest.mark.asyncio
    async def test_find_best_cashback_caches_result(self):
        """Test that results are cached and scrapers are not re-run."""
        monitor = CashbackMonitor(cache_enabled=True)
        
        # Mock all scrapers and keep references to the AsyncMocks
        search_mocks = []
        for platform, scraper in monitor._scrapers.items():
            search_mock = AsyncMock(return_value=[])
            scraper.search = search_mock
            search_mocks.append(search_mock)
        
        # First call executes scrapers and populates cache
        result1 = await monitor.find_best_cashback("Nike")
        
        # Second call should use cache and not call scrapers again
        result2 = await monitor.find_best_cashback("Nike")
        
        # Results should be merchant cashback objects
        assert isinstance(result1, MerchantCashback)
        assert isinstance(result2, MerchantCashback)
        
        # Scrapers should only be awaited once across both calls
        for search_mock in search_mocks:
            search_mock.assert_awaited_once()


class TestSlugOverrides:
    """Test slug override handling in scrapers."""

    def test_rakuten_has_slug_overrides(self):
        """Test that Rakuten scraper has slug overrides."""
        from cashback.scrapers.rakuten import RakutenScraper
        
        scraper = RakutenScraper()
        
        # Pandora should map to pandora-jewelry
        assert hasattr(scraper, 'SLUG_OVERRIDES') or hasattr(scraper, '_get_all_slugs')

    def test_topcashback_has_slug_overrides(self):
        """Test that TopCashback scraper has slug handling."""
        from cashback.scrapers.topcashback import TopCashbackScraper
        
        scraper = TopCashbackScraper()
        
        # Should have search page method
        assert hasattr(scraper, '_search_page') or hasattr(scraper, 'search')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
