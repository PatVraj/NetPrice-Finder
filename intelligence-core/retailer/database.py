"""
SQLite Database Layer for Retailer Intelligence.
Provides persistent storage for cashback offers and promo codes.
"""

import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from .models import (
    Retailer,
    RetailerTier,
    StoredCashbackOffer,
    StoredPromoCode,
    PaymentBonus,
    DiscountType,
    PaymentMethodType,
    normalize_retailer_name,
    is_major_retailer,
)


logger = logging.getLogger(__name__)


# Default database path
DEFAULT_DB_PATH = os.getenv(
    "RETAILER_DB_PATH",
    "/app/data/retailers.db"
)


class RetailerDatabase:
    """
    SQLite database for persistent retailer intelligence storage.
    
    Stores:
    - Retailer registry with tiers
    - All cashback offers from all platforms
    - All promo codes with full context
    - Payment method bonuses
    - Scrape history for analytics
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file. Creates if not exists.
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tables
            cursor.executescript("""
                -- Schema version tracking
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Core retailer registry
                CREATE TABLE IF NOT EXISTS retailers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    domain TEXT,
                    category TEXT,
                    mcc_code TEXT,
                    tier TEXT DEFAULT 'standard',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_scraped_at TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_retailers_normalized 
                ON retailers(normalized_name);
                
                CREATE INDEX IF NOT EXISTS idx_retailers_domain 
                ON retailers(domain);
                
                CREATE INDEX IF NOT EXISTS idx_retailers_tier 
                ON retailers(tier);
                
                -- All cashback offers (not just best)
                CREATE TABLE IF NOT EXISTS cashback_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    cashback_percent REAL,
                    cashback_fixed REAL,
                    cashback_text TEXT,
                    category TEXT,
                    is_elevated BOOLEAN DEFAULT FALSE,
                    terms TEXT,
                    affiliate_url TEXT,
                    confidence REAL DEFAULT 1.0,
                    expires_at TIMESTAMP,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (retailer_id) REFERENCES retailers(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_cashback_retailer 
                ON cashback_offers(retailer_id);
                
                CREATE INDEX IF NOT EXISTS idx_cashback_platform 
                ON cashback_offers(platform);
                
                CREATE INDEX IF NOT EXISTS idx_cashback_scraped 
                ON cashback_offers(scraped_at);
                
                -- All promo codes with context
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    code TEXT NOT NULL,
                    description TEXT,
                    discount_type TEXT,
                    discount_value REAL,
                    minimum_purchase REAL,
                    maximum_discount REAL,
                    verified BOOLEAN DEFAULT FALSE,
                    success_rate REAL,
                    times_used INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (retailer_id) REFERENCES retailers(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_promo_retailer 
                ON promo_codes(retailer_id);
                
                CREATE INDEX IF NOT EXISTS idx_promo_code 
                ON promo_codes(code);
                
                CREATE INDEX IF NOT EXISTS idx_promo_verified 
                ON promo_codes(verified);
                
                -- Unique constraint to avoid duplicate codes
                CREATE UNIQUE INDEX IF NOT EXISTS idx_promo_unique 
                ON promo_codes(retailer_id, source, code);
                
                -- Payment method bonuses
                CREATE TABLE IF NOT EXISTS payment_bonuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer_id INTEGER NOT NULL,
                    method TEXT NOT NULL,
                    bonus_type TEXT,
                    bonus_value REAL,
                    bonus_text TEXT,
                    terms TEXT,
                    expires_at TIMESTAMP,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (retailer_id) REFERENCES retailers(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_payment_retailer 
                ON payment_bonuses(retailer_id);
                
                -- Scrape history for debugging and analytics
                CREATE TABLE IF NOT EXISTS scrape_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer_id INTEGER,
                    platform TEXT,
                    success BOOLEAN,
                    error_message TEXT,
                    duration_ms INTEGER,
                    offers_found INTEGER DEFAULT 0,
                    promos_found INTEGER DEFAULT 0,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (retailer_id) REFERENCES retailers(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_scrape_retailer 
                ON scrape_history(retailer_id);
                
                CREATE INDEX IF NOT EXISTS idx_scrape_time 
                ON scrape_history(scraped_at);
            """)
            
            # Check/update schema version
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row and row[0] else 0
            
            if current_version < self.SCHEMA_VERSION:
                cursor.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (self.SCHEMA_VERSION,)
                )
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    # =========================================================================
    # Retailer Operations
    # =========================================================================
    
    def get_or_create_retailer(
        self,
        name: str,
        domain: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Retailer:
        """
        Get existing retailer or create new one.
        
        Args:
            name: Retailer name (e.g., "Amazon")
            domain: Retailer domain (e.g., "amazon.com")
            category: Product category (e.g., "electronics")
            
        Returns:
            Retailer object with ID
        """
        normalized = normalize_retailer_name(name)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find existing
            cursor.execute(
                "SELECT * FROM retailers WHERE normalized_name = ?",
                (normalized,)
            )
            row = cursor.fetchone()
            
            if row:
                return Retailer(
                    id=row["id"],
                    name=row["name"],
                    normalized_name=row["normalized_name"],
                    domain=row["domain"],
                    category=row["category"],
                    mcc_code=row["mcc_code"],
                    tier=RetailerTier(row["tier"]),
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    last_scraped_at=datetime.fromisoformat(row["last_scraped_at"]) if row["last_scraped_at"] else None,
                )
            
            # Create new retailer
            tier = RetailerTier.MAJOR if is_major_retailer(name) else RetailerTier.STANDARD
            
            cursor.execute("""
                INSERT INTO retailers (name, normalized_name, domain, category, tier)
                VALUES (?, ?, ?, ?, ?)
            """, (name, normalized, domain, category, tier.value))
            
            conn.commit()
            
            return Retailer(
                id=cursor.lastrowid,
                name=name,
                normalized_name=normalized,
                domain=domain,
                category=category,
                tier=tier,
                created_at=datetime.now(),
            )
    
    def get_retailer_by_name(self, name: str) -> Optional[Retailer]:
        """Get retailer by name."""
        normalized = normalize_retailer_name(name)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM retailers WHERE normalized_name = ?",
                (normalized,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return Retailer(
                id=row["id"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                domain=row["domain"],
                category=row["category"],
                mcc_code=row["mcc_code"],
                tier=RetailerTier(row["tier"]),
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                last_scraped_at=datetime.fromisoformat(row["last_scraped_at"]) if row["last_scraped_at"] else None,
            )
    
    def update_retailer_scraped(self, retailer_id: int):
        """Update last_scraped_at timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE retailers SET last_scraped_at = ? WHERE id = ?",
                (datetime.now().isoformat(), retailer_id)
            )
            conn.commit()
    
    def get_stale_retailers(self, max_age_hours: int = 24) -> list[Retailer]:
        """Get retailers that haven't been scraped recently."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM retailers 
                WHERE last_scraped_at IS NULL 
                   OR last_scraped_at < datetime('now', ?)
                ORDER BY 
                    CASE tier 
                        WHEN 'major' THEN 1 
                        WHEN 'standard' THEN 2 
                        ELSE 3 
                    END,
                    last_scraped_at ASC
            """, (f'-{max_age_hours} hours',))
            
            retailers = []
            for row in cursor.fetchall():
                retailers.append(Retailer(
                    id=row["id"],
                    name=row["name"],
                    normalized_name=row["normalized_name"],
                    domain=row["domain"],
                    category=row["category"],
                    mcc_code=row["mcc_code"],
                    tier=RetailerTier(row["tier"]),
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    last_scraped_at=datetime.fromisoformat(row["last_scraped_at"]) if row["last_scraped_at"] else None,
                ))
            
            return retailers
    
    # =========================================================================
    # Cashback Operations
    # =========================================================================
    
    def save_cashback_offers(
        self,
        retailer_id: int,
        platform: str,
        offers: list[StoredCashbackOffer],
        replace_existing: bool = True,
    ):
        """
        Save cashback offers for a retailer/platform.
        
        Args:
            retailer_id: Retailer ID
            platform: Platform name (e.g., "rakuten")
            offers: List of offers to save
            replace_existing: If True, delete old offers for this platform first
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if replace_existing:
                cursor.execute(
                    "DELETE FROM cashback_offers WHERE retailer_id = ? AND platform = ?",
                    (retailer_id, platform)
                )
            
            for offer in offers:
                cursor.execute("""
                    INSERT INTO cashback_offers (
                        retailer_id, platform, cashback_percent, cashback_fixed,
                        cashback_text, category, is_elevated, terms, 
                        affiliate_url, confidence, expires_at, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    retailer_id,
                    platform,
                    offer.cashback_percent,
                    offer.cashback_fixed,
                    offer.cashback_text,
                    offer.category,
                    offer.is_elevated,
                    offer.terms,
                    offer.affiliate_url,
                    offer.confidence,
                    offer.expires_at.isoformat() if offer.expires_at else None,
                    datetime.now().isoformat(),
                ))
            
            conn.commit()
    
    def get_cashback_offers(
        self,
        retailer_id: int,
        platform: Optional[str] = None,
        include_expired: bool = False,
    ) -> list[StoredCashbackOffer]:
        """
        Get all cashback offers for a retailer.
        
        Args:
            retailer_id: Retailer ID
            platform: Optional platform filter
            include_expired: Include expired offers
            
        Returns:
            List of cashback offers sorted by effective rate
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM cashback_offers WHERE retailer_id = ?"
            params = [retailer_id]
            
            if platform:
                query += " AND platform = ?"
                params.append(platform)
            
            if not include_expired:
                query += " AND (expires_at IS NULL OR expires_at > datetime('now'))"
            
            query += " ORDER BY COALESCE(cashback_percent, 0) + COALESCE(cashback_fixed, 0) DESC"
            
            cursor.execute(query, params)
            
            offers = []
            for row in cursor.fetchall():
                offers.append(StoredCashbackOffer(
                    id=row["id"],
                    retailer_id=row["retailer_id"],
                    platform=row["platform"],
                    cashback_percent=row["cashback_percent"],
                    cashback_fixed=row["cashback_fixed"],
                    cashback_text=row["cashback_text"],
                    category=row["category"],
                    is_elevated=bool(row["is_elevated"]),
                    terms=row["terms"],
                    affiliate_url=row["affiliate_url"],
                    confidence=row["confidence"],
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                    scraped_at=datetime.fromisoformat(row["scraped_at"]) if row["scraped_at"] else None,
                ))
            
            return offers
    
    # =========================================================================
    # Promo Code Operations
    # =========================================================================
    
    def save_promo_codes(
        self,
        retailer_id: int,
        source: str,
        codes: list[StoredPromoCode],
        replace_existing: bool = True,
    ):
        """
        Save promo codes for a retailer/source.
        
        Uses UPSERT to avoid duplicates.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if replace_existing:
                cursor.execute(
                    "DELETE FROM promo_codes WHERE retailer_id = ? AND source = ?",
                    (retailer_id, source)
                )
            
            for promo in codes:
                cursor.execute("""
                    INSERT OR REPLACE INTO promo_codes (
                        retailer_id, source, code, description,
                        discount_type, discount_value, minimum_purchase,
                        maximum_discount, verified, success_rate,
                        expires_at, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    retailer_id,
                    source,
                    promo.code,
                    promo.description,
                    promo.discount_type.value if promo.discount_type else None,
                    promo.discount_value,
                    promo.minimum_purchase,
                    promo.maximum_discount,
                    promo.verified,
                    promo.success_rate,
                    promo.expires_at.isoformat() if promo.expires_at else None,
                    datetime.now().isoformat(),
                ))
            
            conn.commit()
    
    def get_promo_codes(
        self,
        retailer_id: int,
        source: Optional[str] = None,
        verified_only: bool = False,
        include_expired: bool = False,
    ) -> list[StoredPromoCode]:
        """
        Get all promo codes for a retailer.
        
        Args:
            retailer_id: Retailer ID
            source: Optional source filter
            verified_only: Only return verified codes
            include_expired: Include expired codes
            
        Returns:
            List of promo codes sorted by effective value
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM promo_codes WHERE retailer_id = ?"
            params = [retailer_id]
            
            if source:
                query += " AND source = ?"
                params.append(source)
            
            if verified_only:
                query += " AND verified = 1"
            
            if not include_expired:
                query += " AND (expires_at IS NULL OR expires_at > datetime('now'))"
            
            query += " ORDER BY COALESCE(discount_value, 0) DESC"
            
            cursor.execute(query, params)
            
            codes = []
            for row in cursor.fetchall():
                discount_type = None
                if row["discount_type"]:
                    try:
                        discount_type = DiscountType(row["discount_type"])
                    except ValueError:
                        pass
                
                codes.append(StoredPromoCode(
                    id=row["id"],
                    retailer_id=row["retailer_id"],
                    source=row["source"],
                    code=row["code"],
                    description=row["description"],
                    discount_type=discount_type,
                    discount_value=row["discount_value"],
                    minimum_purchase=row["minimum_purchase"],
                    maximum_discount=row["maximum_discount"],
                    verified=bool(row["verified"]),
                    success_rate=row["success_rate"],
                    times_used=row["times_used"],
                    last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                    scraped_at=datetime.fromisoformat(row["scraped_at"]) if row["scraped_at"] else None,
                ))
            
            return codes
    
    def mark_promo_used(self, promo_id: int, success: bool = True):
        """Mark a promo code as used and update success rate."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current stats
            cursor.execute(
                "SELECT times_used, success_rate FROM promo_codes WHERE id = ?",
                (promo_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return
            
            times_used = (row["times_used"] or 0) + 1
            old_rate = row["success_rate"] or 0.5
            
            # Update success rate with exponential moving average
            new_rate = old_rate * 0.8 + (1.0 if success else 0.0) * 0.2
            
            cursor.execute("""
                UPDATE promo_codes 
                SET times_used = ?, success_rate = ?, last_used_at = ?, verified = ?
                WHERE id = ?
            """, (times_used, new_rate, datetime.now().isoformat(), success, promo_id))
            
            conn.commit()
    
    # =========================================================================
    # Payment Bonus Operations
    # =========================================================================
    
    def save_payment_bonuses(
        self,
        retailer_id: int,
        bonuses: list[PaymentBonus],
        replace_existing: bool = True,
    ):
        """Save payment method bonuses for a retailer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if replace_existing:
                cursor.execute(
                    "DELETE FROM payment_bonuses WHERE retailer_id = ?",
                    (retailer_id,)
                )
            
            for bonus in bonuses:
                cursor.execute("""
                    INSERT INTO payment_bonuses (
                        retailer_id, method, bonus_type, bonus_value,
                        bonus_text, terms, expires_at, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    retailer_id,
                    bonus.method.value if isinstance(bonus.method, PaymentMethodType) else bonus.method,
                    bonus.bonus_type,
                    bonus.bonus_value,
                    bonus.bonus_text,
                    bonus.terms,
                    bonus.expires_at.isoformat() if bonus.expires_at else None,
                    datetime.now().isoformat(),
                ))
            
            conn.commit()
    
    def get_payment_bonuses(
        self,
        retailer_id: int,
        include_expired: bool = False,
    ) -> list[PaymentBonus]:
        """Get payment method bonuses for a retailer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM payment_bonuses WHERE retailer_id = ?"
            params = [retailer_id]
            
            if not include_expired:
                query += " AND (expires_at IS NULL OR expires_at > datetime('now'))"
            
            cursor.execute(query, params)
            
            bonuses = []
            for row in cursor.fetchall():
                try:
                    method = PaymentMethodType(row["method"])
                except ValueError:
                    method = row["method"]
                
                bonuses.append(PaymentBonus(
                    id=row["id"],
                    retailer_id=row["retailer_id"],
                    method=method,
                    bonus_type=row["bonus_type"],
                    bonus_value=row["bonus_value"],
                    bonus_text=row["bonus_text"],
                    terms=row["terms"],
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                    scraped_at=datetime.fromisoformat(row["scraped_at"]) if row["scraped_at"] else None,
                ))
            
            return bonuses
    
    # =========================================================================
    # Scrape History
    # =========================================================================
    
    def log_scrape(
        self,
        retailer_id: int,
        platform: str,
        success: bool,
        duration_ms: int,
        offers_found: int = 0,
        promos_found: int = 0,
        error_message: Optional[str] = None,
    ):
        """Log a scrape attempt for analytics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scrape_history (
                    retailer_id, platform, success, duration_ms,
                    offers_found, promos_found, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                retailer_id, platform, success, duration_ms,
                offers_found, promos_found, error_message
            ))
            conn.commit()
    
    # =========================================================================
    # Maintenance
    # =========================================================================
    
    def cleanup_expired(self, days_old: int = 30):
        """Remove expired data older than specified days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = f'-{days_old} days'
            
            # Remove old expired cashback offers
            cursor.execute("""
                DELETE FROM cashback_offers 
                WHERE expires_at IS NOT NULL 
                  AND expires_at < datetime('now', ?)
            """, (cutoff,))
            
            # Remove old expired promo codes
            cursor.execute("""
                DELETE FROM promo_codes 
                WHERE expires_at IS NOT NULL 
                  AND expires_at < datetime('now', ?)
            """, (cutoff,))
            
            # Remove old scrape history
            cursor.execute("""
                DELETE FROM scrape_history 
                WHERE scraped_at < datetime('now', ?)
            """, (cutoff,))
            
            conn.commit()
            logger.info(f"Cleaned up data older than {days_old} days")
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute("SELECT COUNT(*) FROM retailers")
            stats["total_retailers"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM retailers WHERE tier = 'major'")
            stats["major_retailers"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM cashback_offers")
            stats["total_cashback_offers"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT platform) FROM cashback_offers")
            stats["platforms_tracked"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM promo_codes")
            stats["total_promo_codes"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM promo_codes WHERE verified = 1")
            stats["verified_promo_codes"] = cursor.fetchone()[0]
            
            return stats
