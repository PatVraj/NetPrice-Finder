"""
Retailer Intelligence - Main Interface.
Unified access to cashback and promo code intelligence with caching.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from .models import (
    Retailer,
    RetailerTier,
    RetailerDeals,
    SavingsStrategy,
    StoredCashbackOffer,
    StoredPromoCode,
    PaymentBonus,
    DiscountType,
    normalize_retailer_name,
    is_major_retailer,
    MAJOR_RETAILERS,
)
from .database import RetailerDatabase
from .cache import RetailerCache, TIER_TTL
from .strategy import StrategyCalculator, calculate_best_strategy


logger = logging.getLogger(__name__)


# TTL thresholds for freshness check (in seconds)
FRESHNESS_THRESHOLDS = {
    "major": 4 * 3600,      # 4 hours
    "standard": 12 * 3600,  # 12 hours
    "minor": 24 * 3600,     # 24 hours
}


class RetailerIntelligence:
    """
    Unified interface for retailer cashback and promo code intelligence.
    
    Provides:
    - Quick access to cached deals for major retailers
    - Persistent storage in SQLite
    - Hot cache in Redis
    - Background refresh for stale data
    - Intelligent strategy calculation
    
    Usage:
        intelligence = RetailerIntelligence()
        await intelligence.initialize()
        
        # Get all deals for a retailer
        deals = await intelligence.get_deals("Amazon")
        
        # Get optimal savings strategy
        strategy = await intelligence.get_best_strategy(
            "Amazon",
            purchase_amount=100.00,
        )
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        card_wallet: Optional[Any] = None,
    ):
        """
        Initialize retailer intelligence.
        
        Args:
            db_path: Path to SQLite database
            redis_host: Redis host
            redis_port: Redis port
            card_wallet: Credit card wallet for strategy calculation
        """
        self.db = RetailerDatabase(db_path)
        self.cache = RetailerCache(host=redis_host, port=redis_port)
        self.card_wallet = card_wallet
        self._initialized = False
        
        # Lazy import to avoid circular dependency
        self._cashback_monitor = None
    
    async def initialize(self):
        """Initialize connections."""
        if self._initialized:
            return
        
        await self.cache.connect()
        self._initialized = True
        logger.info("RetailerIntelligence initialized")
    
    async def close(self):
        """Close connections."""
        await self.cache.close()
        self._initialized = False
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # =========================================================================
    # Main Interface
    # =========================================================================
    
    async def get_deals(
        self,
        retailer: str,
        *,
        include_expired: bool = False,
        force_refresh: bool = False,
    ) -> RetailerDeals:
        """
        Get all deals for a retailer.
        
        Checks cache first, then database, then triggers fresh scrape if needed.
        
        Args:
            retailer: Retailer name (e.g., "Amazon")
            include_expired: Include expired offers/codes
            force_refresh: Force fresh scrape
            
        Returns:
            RetailerDeals with all cashback offers and promo codes
        """
        await self.initialize()
        
        normalized = normalize_retailer_name(retailer)
        
        # 1. Check Redis cache first (unless force refresh)
        if not force_refresh:
            cached = await self.cache.get_deals(normalized)
            if cached:
                # Check if still fresh
                cached_at = datetime.fromisoformat(cached.get("_cached_at", "2000-01-01"))
                tier = cached.get("_tier", "standard")
                threshold = FRESHNESS_THRESHOLDS.get(tier, FRESHNESS_THRESHOLDS["standard"])
                
                if (datetime.now() - cached_at).total_seconds() < threshold:
                    # Convert cached dict back to RetailerDeals
                    return self._dict_to_deals(cached, is_fresh=True)
        
        # 2. Check database
        db_retailer = self.db.get_retailer_by_name(retailer)
        
        if db_retailer:
            # Check if database data is fresh enough
            is_fresh = False
            if db_retailer.last_scraped_at:
                tier = db_retailer.tier.value
                threshold = FRESHNESS_THRESHOLDS.get(tier, FRESHNESS_THRESHOLDS["standard"])
                age = (datetime.now() - db_retailer.last_scraped_at).total_seconds()
                is_fresh = age < threshold
            
            if is_fresh and not force_refresh:
                # Load from database
                deals = await self._load_from_database(db_retailer, include_expired)
                
                # Warm the cache
                await self._cache_deals(deals)
                
                return deals
            
            # Data is stale, trigger background refresh
            if not force_refresh:
                asyncio.create_task(self._background_refresh(retailer))
                
                # Return stale data while refresh happens
                deals = await self._load_from_database(db_retailer, include_expired)
                deals.is_fresh = False
                return deals
        
        # 3. Need fresh scrape
        return await self.refresh_retailer(retailer)
    
    async def get_best_strategy(
        self,
        retailer: str,
        purchase_amount: float,
        *,
        card_wallet: Optional[Any] = None,
        product_category: Optional[str] = None,
    ) -> SavingsStrategy:
        """
        Calculate optimal savings strategy for a purchase.
        
        Args:
            retailer: Retailer name
            purchase_amount: Purchase amount in dollars
            card_wallet: Credit card wallet (uses default if not provided)
            product_category: Product category for CC rewards
            
        Returns:
            SavingsStrategy with ranked options
        """
        deals = await self.get_deals(retailer)
        
        wallet = card_wallet or self.card_wallet
        
        return calculate_best_strategy(
            deals=deals,
            purchase_amount=purchase_amount,
            card_wallet=wallet,
            product_category=product_category,
        )
    
    async def refresh_retailer(
        self,
        retailer: str,
        *,
        platforms: Optional[list[str]] = None,
    ) -> RetailerDeals:
        """
        Force refresh data for a retailer.
        
        Scrapes all platforms and updates database and cache.
        
        Args:
            retailer: Retailer name
            platforms: Specific platforms to refresh (default: all)
            
        Returns:
            Fresh RetailerDeals
        """
        await self.initialize()
        
        # Acquire lock to prevent duplicate scrapes
        if not await self.cache.acquire_scrape_lock(retailer):
            # Already being scraped, return stale data
            logger.info(f"Scrape already in progress for {retailer}")
            db_retailer = self.db.get_retailer_by_name(retailer)
            if db_retailer:
                deals = await self._load_from_database(db_retailer, False)
                deals.is_fresh = False
                return deals
            # No data at all, wait a bit and try again
            await asyncio.sleep(2)
            return await self.get_deals(retailer)
        
        try:
            # Get or create retailer in database
            db_retailer = self.db.get_or_create_retailer(retailer)
            
            # Scrape fresh data
            cashback_offers = []
            promo_codes = []
            data_sources = []
            
            # Use CashbackMonitor for scraping
            monitor = await self._get_cashback_monitor()
            
            try:
                from ..cashback.monitor import CashbackPlatform
                
                # Determine which platforms to scrape
                platforms_to_scrape = platforms or [
                    "rakuten", "topcashback", "honey", "befrugal", "swagbucks"
                ]
                
                # Get fresh data
                merchant_cashback = await monitor.find_best_cashback_and_promos(retailer)
                
                # Convert offers to stored format
                for offer in merchant_cashback.offers:
                    stored_offer = StoredCashbackOffer(
                        retailer_id=db_retailer.id,
                        platform=offer.platform.value,
                        cashback_percent=offer.cashback_percent,
                        cashback_fixed=offer.cashback_fixed,
                        cashback_text=offer.cashback_text,
                        category=offer.category,
                        is_elevated=offer.is_elevated,
                        terms=offer.terms,
                        affiliate_url=offer.affiliate_url,
                        confidence=offer.confidence,
                        scraped_at=datetime.now(),
                    )
                    cashback_offers.append(stored_offer)
                    
                    if offer.platform.value not in data_sources:
                        data_sources.append(offer.platform.value)
                
                # Convert promo codes to stored format
                for promo in merchant_cashback.promo_codes:
                    # Parse discount type
                    discount_type = None
                    discount_value = None
                    
                    if promo.discount_percent:
                        discount_type = DiscountType.PERCENT
                        discount_value = promo.discount_percent
                    elif promo.discount_amount:
                        discount_type = DiscountType.FIXED
                        discount_value = promo.discount_amount
                    
                    stored_promo = StoredPromoCode(
                        retailer_id=db_retailer.id,
                        source=promo.platform.value,
                        code=promo.code,
                        description=promo.description,
                        discount_type=discount_type,
                        discount_value=discount_value,
                        minimum_purchase=promo.minimum_purchase,
                        verified=promo.verified,
                        success_rate=promo.success_rate,
                        scraped_at=datetime.now(),
                    )
                    promo_codes.append(stored_promo)
                    
            except Exception as e:
                logger.error(f"Error scraping {retailer}: {e}")
            
            # Save to database
            for platform in data_sources:
                platform_offers = [o for o in cashback_offers if o.platform == platform]
                platform_promos = [p for p in promo_codes if p.source == platform]
                
                if platform_offers:
                    self.db.save_cashback_offers(
                        db_retailer.id, platform, platform_offers
                    )
                if platform_promos:
                    self.db.save_promo_codes(
                        db_retailer.id, platform, platform_promos
                    )
                
                # Log scrape
                self.db.log_scrape(
                    retailer_id=db_retailer.id,
                    platform=platform,
                    success=True,
                    duration_ms=0,  # TODO: track duration
                    offers_found=len(platform_offers),
                    promos_found=len(platform_promos),
                )
            
            # Update retailer scraped timestamp
            self.db.update_retailer_scraped(db_retailer.id)
            
            # Build deals object
            deals = RetailerDeals(
                retailer=retailer,
                retailer_id=db_retailer.id,
                tier=db_retailer.tier,
                cashback_offers=cashback_offers,
                promo_codes=promo_codes,
                payment_bonuses=[],  # TODO: scrape payment bonuses
                cached_at=datetime.now(),
                is_fresh=True,
                data_sources=data_sources,
            )
            
            # Update cache
            await self._cache_deals(deals)
            
            return deals
            
        finally:
            await self.cache.release_scrape_lock(retailer)
    
    async def get_stale_retailers(
        self,
        max_age_hours: int = 24,
    ) -> list[str]:
        """Get list of retailers needing refresh."""
        stale = self.db.get_stale_retailers(max_age_hours)
        return [r.name for r in stale]
    
    async def register_major_retailer(
        self,
        name: str,
        domain: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Retailer:
        """
        Register a retailer as 'major' for priority refreshes.
        
        Args:
            name: Retailer name
            domain: Retailer domain
            category: Product category
            
        Returns:
            Retailer object
        """
        retailer = self.db.get_or_create_retailer(name, domain, category)
        
        # Update tier to major
        if retailer.tier != RetailerTier.MAJOR:
            # TODO: Add update_tier method to database
            pass
        
        return retailer
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    async def _get_cashback_monitor(self):
        """Get or create CashbackMonitor instance."""
        if self._cashback_monitor is None:
            from ..cashback.monitor import CashbackMonitor
            self._cashback_monitor = CashbackMonitor(cache_enabled=False)
        return self._cashback_monitor
    
    async def _load_from_database(
        self,
        retailer: Retailer,
        include_expired: bool = False,
    ) -> RetailerDeals:
        """Load deals from database."""
        cashback_offers = self.db.get_cashback_offers(
            retailer.id,
            include_expired=include_expired,
        )
        
        promo_codes = self.db.get_promo_codes(
            retailer.id,
            include_expired=include_expired,
        )
        
        payment_bonuses = self.db.get_payment_bonuses(
            retailer.id,
            include_expired=include_expired,
        )
        
        # Get unique data sources
        data_sources = list(set(
            [o.platform for o in cashback_offers] +
            [p.source for p in promo_codes]
        ))
        
        return RetailerDeals(
            retailer=retailer.name,
            retailer_id=retailer.id,
            tier=retailer.tier,
            cashback_offers=cashback_offers,
            promo_codes=promo_codes,
            payment_bonuses=payment_bonuses,
            cached_at=retailer.last_scraped_at,
            is_fresh=True,
            data_sources=data_sources,
        )
    
    async def _cache_deals(self, deals: RetailerDeals):
        """Cache deals in Redis."""
        await self.cache.set_deals(
            retailer=deals.retailer,
            deals=deals.to_dict(),
            tier=deals.tier.value,
        )
    
    async def _background_refresh(self, retailer: str):
        """Background task to refresh retailer data."""
        try:
            logger.info(f"Background refresh started for {retailer}")
            await self.refresh_retailer(retailer)
            logger.info(f"Background refresh completed for {retailer}")
        except Exception as e:
            logger.error(f"Background refresh failed for {retailer}: {e}")
    
    def _dict_to_deals(self, data: dict, is_fresh: bool = True) -> RetailerDeals:
        """Convert cached dict back to RetailerDeals."""
        cashback_offers = []
        for o in data.get("cashback_offers", []):
            offer = StoredCashbackOffer(
                id=o.get("id"),
                retailer_id=o.get("retailer_id", 0),
                platform=o.get("platform", ""),
                cashback_percent=o.get("cashback_percent"),
                cashback_fixed=o.get("cashback_fixed"),
                cashback_text=o.get("cashback_text", ""),
                category=o.get("category"),
                is_elevated=o.get("is_elevated", False),
                terms=o.get("terms"),
                affiliate_url=o.get("affiliate_url"),
                confidence=o.get("confidence", 1.0),
            )
            cashback_offers.append(offer)
        
        promo_codes = []
        for p in data.get("promo_codes", []):
            discount_type = None
            if p.get("discount_type"):
                try:
                    discount_type = DiscountType(p["discount_type"])
                except ValueError:
                    pass
            
            promo = StoredPromoCode(
                id=p.get("id"),
                retailer_id=p.get("retailer_id", 0),
                source=p.get("source", ""),
                code=p.get("code", ""),
                description=p.get("description", ""),
                discount_type=discount_type,
                discount_value=p.get("discount_value"),
                minimum_purchase=p.get("minimum_purchase"),
                maximum_discount=p.get("maximum_discount"),
                verified=p.get("verified", False),
                success_rate=p.get("success_rate"),
                times_used=p.get("times_used", 0),
            )
            promo_codes.append(promo)
        
        payment_bonuses = []
        for b in data.get("payment_bonuses", []):
            bonus = PaymentBonus(
                id=b.get("id"),
                retailer_id=b.get("retailer_id", 0),
                method=b.get("method", "paypal"),
                bonus_type=b.get("bonus_type", "cashback"),
                bonus_value=b.get("bonus_value", 0.0),
                bonus_text=b.get("bonus_text", ""),
                terms=b.get("terms"),
            )
            payment_bonuses.append(bonus)
        
        tier = RetailerTier.STANDARD
        if data.get("tier"):
            try:
                tier = RetailerTier(data["tier"])
            except ValueError:
                pass
        
        cached_at = None
        if data.get("cached_at"):
            try:
                cached_at = datetime.fromisoformat(data["cached_at"])
            except ValueError:
                pass
        
        return RetailerDeals(
            retailer=data.get("retailer", ""),
            retailer_id=data.get("retailer_id", 0),
            tier=tier,
            cashback_offers=cashback_offers,
            promo_codes=promo_codes,
            payment_bonuses=payment_bonuses,
            cached_at=cached_at,
            is_fresh=is_fresh,
            data_sources=data.get("data_sources", []),
        )
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    async def get_stats(self) -> dict:
        """Get intelligence system statistics."""
        db_stats = self.db.get_stats()
        cache_stats = await self.cache.get_cache_stats()
        
        return {
            "database": db_stats,
            "cache": cache_stats,
            "major_retailers_count": len(MAJOR_RETAILERS),
        }


# =============================================================================
# Background Worker
# =============================================================================

async def background_refresh_worker(
    intelligence: RetailerIntelligence,
    interval_seconds: int = 1800,  # 30 minutes
    max_per_cycle: int = 5,
):
    """
    Background worker that refreshes stale major retailers.
    
    Args:
        intelligence: RetailerIntelligence instance
        interval_seconds: Time between refresh cycles
        max_per_cycle: Max retailers to refresh per cycle
    """
    logger.info(f"Background refresh worker started (interval: {interval_seconds}s)")
    
    while True:
        try:
            # Get stale major retailers
            stale = await intelligence.get_stale_retailers(max_age_hours=4)
            major_stale = [
                r for r in stale 
                if normalize_retailer_name(r) in MAJOR_RETAILERS
            ]
            
            if major_stale:
                logger.info(f"Found {len(major_stale)} stale major retailers")
                
                for retailer in major_stale[:max_per_cycle]:
                    try:
                        await intelligence.refresh_retailer(retailer)
                        logger.info(f"Refreshed {retailer}")
                        await asyncio.sleep(10)  # Rate limit between scrapes
                    except Exception as e:
                        logger.warning(f"Failed to refresh {retailer}: {e}")
            
        except Exception as e:
            logger.error(f"Background worker error: {e}")
        
        await asyncio.sleep(interval_seconds)


# =============================================================================
# Singleton Instance
# =============================================================================

_instance: Optional[RetailerIntelligence] = None


async def get_intelligence() -> RetailerIntelligence:
    """Get or create singleton RetailerIntelligence instance."""
    global _instance
    
    if _instance is None:
        _instance = RetailerIntelligence()
        await _instance.initialize()
    
    return _instance
