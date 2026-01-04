"""
Redis Cache Layer for Retailer Intelligence.
Provides hot caching with TTL-based invalidation.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


logger = logging.getLogger(__name__)


# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# TTL configuration by retailer tier (in seconds)
TIER_TTL = {
    "major": 4 * 3600,      # 4 hours
    "standard": 12 * 3600,  # 12 hours
    "minor": 24 * 3600,     # 24 hours
}

# Key prefixes
KEY_PREFIX = "retailer:"
DEALS_PREFIX = f"{KEY_PREFIX}deals:"
CASHBACK_PREFIX = f"{KEY_PREFIX}cashback:"
PROMO_PREFIX = f"{KEY_PREFIX}promo:"
LOCK_PREFIX = f"{KEY_PREFIX}lock:"
META_PREFIX = f"{KEY_PREFIX}meta:"


class RetailerCache:
    """
    Redis-based hot cache for retailer intelligence.
    
    Features:
    - Tier-based TTL (major retailers cached shorter for freshness)
    - Structured key hierarchy
    - Lock mechanism to prevent duplicate scrapes
    - Automatic serialization/deserialization
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """
        Initialize Redis cache connection.
        
        Args:
            host: Redis host (default from env)
            port: Redis port (default from env)
        """
        self.host = host or REDIS_HOST
        self.port = port or REDIS_PORT
        self._client = None  # Redis client instance
        self._connected = False
    
    async def connect(self) -> bool:
        """
        Establish Redis connection.
        
        Returns:
            True if connected successfully
        """
        if redis is None:
            logger.warning("redis package not installed, cache disabled")
            return False
        
        if self._client and self._connected:
            return True
        
        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
    
    async def _ensure_connected(self) -> bool:
        """Ensure connection is active."""
        if not self._connected:
            return await self.connect()
        return True
    
    # =========================================================================
    # Key Helpers
    # =========================================================================
    
    @staticmethod
    def _normalize_key(retailer: str) -> str:
        """Normalize retailer name for cache key."""
        return retailer.lower().strip().replace(" ", "")
    
    @staticmethod
    def _serialize(data: Any) -> str:
        """Serialize data for Redis storage."""
        return json.dumps(data, default=str)
    
    @staticmethod
    def _deserialize(data: str) -> Any:
        """Deserialize data from Redis."""
        return json.loads(data)
    
    def _get_ttl(self, tier: str) -> int:
        """Get TTL in seconds for a retailer tier."""
        return TIER_TTL.get(tier, TIER_TTL["standard"])
    
    # =========================================================================
    # Deals Cache (Aggregated)
    # =========================================================================
    
    async def get_deals(self, retailer: str) -> Optional[dict]:
        """
        Get cached deals for a retailer.
        
        Args:
            retailer: Retailer name
            
        Returns:
            Cached deals dict or None if not cached/expired
        """
        if not await self._ensure_connected():
            return None
        
        key = f"{DEALS_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            data = await self._client.get(key)
            if data:
                return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        
        return None
    
    async def set_deals(
        self,
        retailer: str,
        deals: dict,
        tier: str = "standard",
    ):
        """
        Cache deals for a retailer.
        
        Args:
            retailer: Retailer name
            deals: Deals dictionary to cache
            tier: Retailer tier for TTL
        """
        if not await self._ensure_connected():
            return
        
        key = f"{DEALS_PREFIX}{self._normalize_key(retailer)}"
        ttl = self._get_ttl(tier)
        
        # Add cache metadata
        deals["_cached_at"] = datetime.now().isoformat()
        deals["_tier"] = tier
        
        try:
            await self._client.setex(key, ttl, self._serialize(deals))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def invalidate_deals(self, retailer: str):
        """Invalidate cached deals for a retailer."""
        if not await self._ensure_connected():
            return
        
        key = f"{DEALS_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")
    
    # =========================================================================
    # Platform-Specific Cache
    # =========================================================================
    
    async def get_cashback(
        self,
        retailer: str,
        platform: str,
    ) -> Optional[list[dict]]:
        """Get cached cashback offers for a specific platform."""
        if not await self._ensure_connected():
            return None
        
        key = f"{CASHBACK_PREFIX}{self._normalize_key(retailer)}:{platform}"
        
        try:
            data = await self._client.get(key)
            if data:
                return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        
        return None
    
    async def set_cashback(
        self,
        retailer: str,
        platform: str,
        offers: list[dict],
        tier: str = "standard",
    ):
        """Cache cashback offers for a specific platform."""
        if not await self._ensure_connected():
            return
        
        key = f"{CASHBACK_PREFIX}{self._normalize_key(retailer)}:{platform}"
        ttl = self._get_ttl(tier)
        
        try:
            await self._client.setex(key, ttl, self._serialize(offers))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def get_promos(
        self,
        retailer: str,
        source: str,
    ) -> Optional[list[dict]]:
        """Get cached promo codes for a specific source."""
        if not await self._ensure_connected():
            return None
        
        key = f"{PROMO_PREFIX}{self._normalize_key(retailer)}:{source}"
        
        try:
            data = await self._client.get(key)
            if data:
                return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        
        return None
    
    async def set_promos(
        self,
        retailer: str,
        source: str,
        promos: list[dict],
        tier: str = "standard",
    ):
        """Cache promo codes for a specific source."""
        if not await self._ensure_connected():
            return
        
        key = f"{PROMO_PREFIX}{self._normalize_key(retailer)}:{source}"
        ttl = self._get_ttl(tier)
        
        try:
            await self._client.setex(key, ttl, self._serialize(promos))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    # =========================================================================
    # Scrape Locking
    # =========================================================================
    
    async def acquire_scrape_lock(
        self,
        retailer: str,
        platform: Optional[str] = None,
        ttl_seconds: int = 300,  # 5 minutes
    ) -> bool:
        """
        Acquire a lock to prevent duplicate scrapes.
        
        Args:
            retailer: Retailer name
            platform: Optional platform (for platform-specific locks)
            ttl_seconds: Lock TTL
            
        Returns:
            True if lock acquired, False if already locked
        """
        if not await self._ensure_connected():
            return True  # Allow scrape if no cache
        
        if platform:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}:{platform}"
        else:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            # SET NX (only if not exists)
            result = await self._client.set(key, "1", nx=True, ex=ttl_seconds)
            return result is not None
        except Exception as e:
            logger.warning(f"Lock acquire error: {e}")
            return True  # Allow scrape on error
    
    async def release_scrape_lock(
        self,
        retailer: str,
        platform: Optional[str] = None,
    ):
        """Release a scrape lock."""
        if not await self._ensure_connected():
            return
        
        if platform:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}:{platform}"
        else:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.warning(f"Lock release error: {e}")
    
    async def is_locked(
        self,
        retailer: str,
        platform: Optional[str] = None,
    ) -> bool:
        """Check if a retailer/platform is currently being scraped."""
        if not await self._ensure_connected():
            return False
        
        if platform:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}:{platform}"
        else:
            key = f"{LOCK_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Lock check error: {e}")
            return False
    
    # =========================================================================
    # Metadata
    # =========================================================================
    
    async def get_retailer_meta(self, retailer: str) -> Optional[dict]:
        """Get cached retailer metadata."""
        if not await self._ensure_connected():
            return None
        
        key = f"{META_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            data = await self._client.get(key)
            if data:
                return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        
        return None
    
    async def set_retailer_meta(
        self,
        retailer: str,
        meta: dict,
        ttl_seconds: int = 3600,  # 1 hour
    ):
        """Cache retailer metadata."""
        if not await self._ensure_connected():
            return
        
        key = f"{META_PREFIX}{self._normalize_key(retailer)}"
        
        try:
            await self._client.setex(key, ttl_seconds, self._serialize(meta))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    # =========================================================================
    # Bulk Operations
    # =========================================================================
    
    async def invalidate_all(self, retailer: str):
        """Invalidate all cached data for a retailer."""
        if not await self._ensure_connected():
            return
        
        normalized = self._normalize_key(retailer)
        patterns = [
            f"{DEALS_PREFIX}{normalized}",
            f"{CASHBACK_PREFIX}{normalized}:*",
            f"{PROMO_PREFIX}{normalized}:*",
            f"{META_PREFIX}{normalized}",
        ]
        
        try:
            for pattern in patterns:
                if "*" in pattern:
                    # Use SCAN for pattern matching
                    async for key in self._client.scan_iter(match=pattern):
                        await self._client.delete(key)
                else:
                    await self._client.delete(pattern)
        except Exception as e:
            logger.warning(f"Cache invalidate all error: {e}")
    
    async def get_cached_retailers(self) -> list[str]:
        """Get list of all cached retailers."""
        if not await self._ensure_connected():
            return []
        
        retailers = set()
        pattern = f"{DEALS_PREFIX}*"
        
        try:
            async for key in self._client.scan_iter(match=pattern):
                # Extract retailer name from key
                retailer = key.replace(DEALS_PREFIX, "")
                retailers.add(retailer)
        except Exception as e:
            logger.warning(f"Cache scan error: {e}")
        
        return list(retailers)
    
    async def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        if not await self._ensure_connected():
            return {"connected": False}
        
        try:
            info = await self._client.info("memory")
            keys_deals = 0
            keys_cashback = 0
            keys_promos = 0
            
            async for _ in self._client.scan_iter(match=f"{DEALS_PREFIX}*"):
                keys_deals += 1
            async for _ in self._client.scan_iter(match=f"{CASHBACK_PREFIX}*"):
                keys_cashback += 1
            async for _ in self._client.scan_iter(match=f"{PROMO_PREFIX}*"):
                keys_promos += 1
            
            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "unknown"),
                "cached_retailers": keys_deals,
                "cached_cashback_entries": keys_cashback,
                "cached_promo_entries": keys_promos,
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"connected": False, "error": str(e)}
