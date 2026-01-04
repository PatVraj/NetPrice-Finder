"""
SQLite Database Layer for User Management.
Provides persistent storage for users, card wallets, and search history.
"""

import os
import sqlite3
import logging
import secrets
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict

# Optional: Use bcrypt if available
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logging.warning(
        "⚠️ bcrypt not installed. Using SHA256 for password hashing. "
        "For production, install bcrypt: pip install bcrypt"
    )

# Demo mode flag - only in demo mode can $demo$ passwords authenticate
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

logger = logging.getLogger(__name__)


# Default database path
DEFAULT_DB_PATH = os.getenv(
    "USER_DB_PATH",
    "/app/data/users.db"
)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class User:
    """User account model."""
    id: int
    email: str
    password_hash: str
    is_admin: bool = False
    tax_rate: Optional[float] = None  # User's preferred tax rate
    location: Optional[str] = None  # User's location (state/city)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class UserCard:
    """Credit card in user's wallet."""
    id: int
    user_id: int
    card_id: str  # References POPULAR_CARDS key or "custom"
    name: str
    issuer: str
    base_rate: float
    bonus_categories: List[Dict[str, Any]] = field(default_factory=list)
    is_custom: bool = False
    created_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "card_id": self.card_id,
            "name": self.name,
            "issuer": self.issuer,
            "base_rate": self.base_rate,
            "bonus_categories": self.bonus_categories,
            "is_custom": self.is_custom,
        }


@dataclass
class SearchHistory:
    """User's search history entry."""
    id: int
    user_id: int
    product_url: str
    product_name: Optional[str]
    retailer: Optional[str]
    product_price: float
    net_price: float
    total_savings: float
    best_cashback_platform: Optional[str]
    best_cashback_rate: float
    searched_at: str


@dataclass
class PricePoint:
    """A single price observation for a product."""
    id: int
    product_id: int
    price: float
    net_price: float
    best_cashback_rate: float
    recorded_at: str
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "price": self.price,
            "net_price": self.net_price,
            "best_cashback_rate": self.best_cashback_rate,
            "recorded_at": self.recorded_at,
        }


@dataclass
class TrackedProduct:
    """A product being tracked for price history."""
    id: int
    user_id: int
    product_url: str
    product_name: Optional[str]
    retailer: Optional[str]
    
    # Current price snapshot
    current_price: Optional[float] = None
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    
    # Alert settings
    target_price: Optional[float] = None  # Alert when price drops below
    alert_enabled: bool = False
    
    # Timestamps
    first_tracked_at: str = ""
    last_checked_at: str = ""
    
    # Price history (populated separately)
    price_history: List[PricePoint] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "product_url": self.product_url,
            "product_name": self.product_name,
            "retailer": self.retailer,
            "current_price": self.current_price,
            "lowest_price": self.lowest_price,
            "highest_price": self.highest_price,
            "target_price": self.target_price,
            "alert_enabled": self.alert_enabled,
            "first_tracked_at": self.first_tracked_at,
            "last_checked_at": self.last_checked_at,
            "price_history": [p.to_dict() for p in self.price_history],
            "price_drop_percent": self._calculate_drop_percent(),
        }
    
    def _calculate_drop_percent(self) -> Optional[float]:
        """Calculate percentage drop from highest to current."""
        if (
            self.highest_price is not None
            and self.current_price is not None
            and self.highest_price > 0
        ):
            drop = ((self.highest_price - self.current_price) / self.highest_price) * 100
            return round(drop, 1) if drop > 0 else 0.0
        return None


# =============================================================================
# Password Hashing
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt (preferred) or SHA256 with salt."""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    else:
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"$sha256${salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash.
    
    Handles:
    - bcrypt hashes ($2a$, $2b$, etc.)
    - SHA256 with salt fallback ($sha256$salt$hash)
    - Demo passwords ($demo$password) - ONLY when DEMO_MODE is enabled
    
    Returns False for malformed or unrecognized hash formats.
    """
    # Guard against None or non-string inputs
    if not password_hash or not isinstance(password_hash, str):
        return False
    
    # Handle demo user special case - ONLY when DEMO_MODE is enabled
    if password_hash.startswith("$demo$"):
        if not DEMO_MODE:
            logger.warning("Demo password attempted outside DEMO_MODE")
            return False
        return password == password_hash[6:]
    
    # bcrypt hashes
    if BCRYPT_AVAILABLE and password_hash.startswith("$2"):
        # Validate bcrypt hash length (minimum 59 chars)
        if len(password_hash) < 59:
            return False
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False
    
    # SHA256 with salt fallback
    if password_hash.startswith("$sha256$"):
        parts = password_hash.split("$")
        if len(parts) != 4:
            return False
        salt = parts[2]
        stored_hash = parts[3]
        if not salt or not stored_hash:
            return False
        computed = hashlib.sha256((salt + password).encode()).hexdigest()
        return computed == stored_hash
    
    # Unrecognized format
    return False


# =============================================================================
# Database Layer
# =============================================================================

class UserDatabase:
    """
    SQLite database for persistent user data storage.
    
    Stores:
    - User accounts with hashed passwords
    - Credit card wallets per user
    - Search history per user
    - User preferences (tax rate, location)
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
        
        logger.info(f"UserDatabase initialized at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # =========================================================================
    # Row Mapping Helpers
    # =========================================================================
    
    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        """Convert a database row to a User object."""
        return User(
            id=row["id"],
            email=row["email"],
            password_hash=row["password_hash"],
            is_admin=bool(row["is_admin"]),
            tax_rate=row["tax_rate"],
            location=row["location"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> UserCard:
        """Convert a database row to a UserCard object."""
        import json
        bonus = json.loads(row["bonus_categories"]) if row["bonus_categories"] else []
        return UserCard(
            id=row["id"],
            user_id=row["user_id"],
            card_id=row["card_id"],
            name=row["name"],
            issuer=row["issuer"],
            base_rate=row["base_rate"],
            bonus_categories=bonus,
            is_custom=bool(row["is_custom"]),
            created_at=row["created_at"]
        )
    
    @staticmethod
    def _serialize_bonus_categories(bonus_categories: Optional[List[dict]]) -> Optional[str]:
        """Serialize bonus categories to JSON for storage."""
        import json
        if bonus_categories:
            return json.dumps(bonus_categories)
        return None
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.executescript("""
                -- Schema version tracking
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- User accounts
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    tax_rate REAL,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- User's credit card wallet
                CREATE TABLE IF NOT EXISTS user_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    card_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    base_rate REAL DEFAULT 1.0,
                    bonus_categories TEXT,  -- JSON array
                    is_custom BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, card_id)
                );
                
                -- Search history
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_url TEXT NOT NULL,
                    product_name TEXT,
                    retailer TEXT,
                    product_price REAL NOT NULL,
                    net_price REAL NOT NULL,
                    total_savings REAL DEFAULT 0,
                    best_cashback_platform TEXT,
                    best_cashback_rate REAL DEFAULT 0,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                
                -- Tracked products for price monitoring
                CREATE TABLE IF NOT EXISTS tracked_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_url TEXT NOT NULL,
                    product_name TEXT,
                    retailer TEXT,
                    current_price REAL,
                    lowest_price REAL,
                    highest_price REAL,
                    target_price REAL,  -- Alert when price drops below this
                    alert_enabled BOOLEAN DEFAULT FALSE,
                    first_tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, product_url)
                );
                
                -- Price history observations
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    net_price REAL NOT NULL,
                    best_cashback_rate REAL DEFAULT 0,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES tracked_products(id) ON DELETE CASCADE
                );
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_user_cards_user ON user_cards(user_id);
                CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);
                CREATE INDEX IF NOT EXISTS idx_search_history_date ON search_history(searched_at);
                CREATE INDEX IF NOT EXISTS idx_tracked_products_user ON tracked_products(user_id);
                CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id);
                CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(recorded_at);
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
                logger.info(f"Database schema updated to version {self.SCHEMA_VERSION}")
    
    # =========================================================================
    # User Management
    # =========================================================================
    
    def create_user(
        self,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> Optional[User]:
        """
        Create a new user account.
        
        Returns:
            User object if created, None if email already exists.
        """
        password_hash = hash_password(password)
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO users (email, password_hash, is_admin, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (email.lower(), password_hash, is_admin, now, now))
                conn.commit()
                
                user_id = cursor.lastrowid
                logger.info(f"Created user: {email} (id={user_id})")
                
                return User(
                    id=user_id,
                    email=email.lower(),
                    password_hash=password_hash,
                    is_admin=is_admin,
                    created_at=now,
                    updated_at=now
                )
            except sqlite3.IntegrityError:
                logger.warning(f"User already exists: {email}")
                return None
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE email = ?",
                (email.lower(),)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_user(row)
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_user(row)
            return None
    
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user with email and password.
        
        Returns:
            User object if authentication succeeds, None otherwise.
        """
        user = self.get_user_by_email(email)
        if user and verify_password(password, user.password_hash):
            logger.info(f"User authenticated: {email}")
            return user
        logger.warning(f"Authentication failed for: {email}")
        return None
    
    # Sentinel value to indicate "clear this field" vs "don't update"
    _CLEAR_VALUE = object()
    
    def update_user_settings(
        self,
        user_id: int,
        tax_rate: Optional[float] = None,
        location: Optional[str] = None,
        clear_tax_rate: bool = False,
    ) -> bool:
        """
        Update user's preferences.
        
        Args:
            user_id: User ID to update
            tax_rate: New tax rate (None = don't change, use clear_tax_rate to clear)
            location: New location (None = don't change)
            clear_tax_rate: If True, clears the tax_rate to NULL (for auto-detection)
        """
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Use parameterized update - no string concatenation
            if clear_tax_rate:
                # Clear tax rate to NULL
                cursor.execute(
                    "UPDATE users SET tax_rate = NULL, updated_at = ? WHERE id = ?",
                    (now, user_id)
                )
            elif tax_rate is not None and location is not None:
                cursor.execute(
                    "UPDATE users SET tax_rate = ?, location = ?, updated_at = ? WHERE id = ?",
                    (tax_rate, location, now, user_id)
                )
            elif tax_rate is not None:
                cursor.execute(
                    "UPDATE users SET tax_rate = ?, updated_at = ? WHERE id = ?",
                    (tax_rate, now, user_id)
                )
            elif location is not None:
                cursor.execute(
                    "UPDATE users SET location = ?, updated_at = ? WHERE id = ?",
                    (location, now, user_id)
                )
            else:
                # No changes
                return True
            
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_users(self) -> List[User]:
        """Get all users (admin function)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
            
            return [self._row_to_user(row) for row in cursor.fetchall()]
    
    def get_user_count(self) -> int:
        """Get total number of users."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
    
    # =========================================================================
    # Card Wallet Management
    # =========================================================================
    
    def add_card_to_wallet(
        self,
        user_id: int,
        card_id: str,
        name: str,
        issuer: str,
        base_rate: float = 1.0,
        bonus_categories: Optional[List[Dict]] = None,
        is_custom: bool = False
    ) -> Optional[UserCard]:
        """
        Add a credit card to user's wallet.
        
        Returns:
            UserCard if added, None if already exists.
        """
        now = datetime.now().isoformat()
        bonus_json = self._serialize_bonus_categories(bonus_categories) or "[]"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO user_cards 
                    (user_id, card_id, name, issuer, base_rate, bonus_categories, is_custom, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, card_id, name, issuer, base_rate, bonus_json, is_custom, now))
                conn.commit()
                
                card = UserCard(
                    id=cursor.lastrowid,
                    user_id=user_id,
                    card_id=card_id,
                    name=name,
                    issuer=issuer,
                    base_rate=base_rate,
                    bonus_categories=bonus_categories or [],
                    is_custom=is_custom,
                    created_at=now
                )
                logger.info(f"Added card {name} to user {user_id}'s wallet")
                return card
            except sqlite3.IntegrityError:
                logger.warning(f"Card {card_id} already in user {user_id}'s wallet")
                return None
    
    def get_user_cards(self, user_id: int) -> List[UserCard]:
        """Get all cards in a user's wallet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_cards WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            )
            
            return [self._row_to_card(row) for row in cursor.fetchall()]
    
    def remove_card_from_wallet(self, user_id: int, card_id: str) -> bool:
        """Remove a card from user's wallet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_cards WHERE user_id = ? AND card_id = ?",
                (user_id, card_id)
            )
            conn.commit()
            removed = cursor.rowcount > 0
            if removed:
                logger.info(f"Removed card {card_id} from user {user_id}'s wallet")
            return removed
    
    def clear_user_wallet(self, user_id: int) -> int:
        """Remove all cards from user's wallet. Returns count removed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_cards WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount
    
    # =========================================================================
    # Search History
    # =========================================================================
    
    def add_search_history(
        self,
        user_id: int,
        product_url: str,
        product_price: float,
        net_price: float,
        product_name: Optional[str] = None,
        retailer: Optional[str] = None,
        total_savings: float = 0,
        best_cashback_platform: Optional[str] = None,
        best_cashback_rate: float = 0
    ) -> SearchHistory:
        """Add a search to user's history."""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO search_history 
                (user_id, product_url, product_name, retailer, product_price, 
                 net_price, total_savings, best_cashback_platform, best_cashback_rate, searched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, product_url, product_name, retailer, product_price,
                net_price, total_savings, best_cashback_platform, best_cashback_rate, now
            ))
            conn.commit()
            
            return SearchHistory(
                id=cursor.lastrowid,
                user_id=user_id,
                product_url=product_url,
                product_name=product_name,
                retailer=retailer,
                product_price=product_price,
                net_price=net_price,
                total_savings=total_savings,
                best_cashback_platform=best_cashback_platform,
                best_cashback_rate=best_cashback_rate,
                searched_at=now
            )
    
    def get_user_search_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[SearchHistory]:
        """Get user's recent search history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM search_history 
                WHERE user_id = ? 
                ORDER BY searched_at DESC 
                LIMIT ?
            """, (user_id, limit))
            
            return [
                SearchHistory(
                    id=row["id"],
                    user_id=row["user_id"],
                    product_url=row["product_url"],
                    product_name=row["product_name"],
                    retailer=row["retailer"],
                    product_price=row["product_price"],
                    net_price=row["net_price"],
                    total_savings=row["total_savings"],
                    best_cashback_platform=row["best_cashback_platform"],
                    best_cashback_rate=row["best_cashback_rate"],
                    searched_at=row["searched_at"]
                )
                for row in cursor.fetchall()
            ]
    
    def get_total_searches(self) -> int:
        """Get total number of searches across all users."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM search_history")
            return cursor.fetchone()[0]
    
    def get_top_retailers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most searched retailers."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT retailer, COUNT(*) as count 
                FROM search_history 
                WHERE retailer IS NOT NULL 
                GROUP BY retailer 
                ORDER BY count DESC 
                LIMIT ?
            """, (limit,))
            
            return [
                {"retailer": row["retailer"], "count": row["count"]}
                for row in cursor.fetchall()
            ]
    
    def get_user_savings_stats(self, user_id: int) -> Dict[str, Any]:
        """Get aggregate savings stats for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_searches,
                    SUM(total_savings) as total_saved,
                    AVG(total_savings) as avg_savings,
                    MAX(total_savings) as best_savings
                FROM search_history
                WHERE user_id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            return {
                "total_searches": row["total_searches"] or 0,
                "total_saved": row["total_saved"] or 0,
                "avg_savings": row["avg_savings"] or 0,
                "best_savings": row["best_savings"] or 0
            }
    
    # =========================================================================
    # Price Tracking
    # =========================================================================
    
    def track_product(
        self,
        user_id: int,
        product_url: str,
        product_name: Optional[str] = None,
        retailer: Optional[str] = None,
        initial_price: Optional[float] = None,
        net_price: Optional[float] = None,
        cashback_rate: float = 0.0,
        target_price: Optional[float] = None,
    ) -> Optional[TrackedProduct]:
        """
        Start tracking a product's price for a user.
        If already tracking, updates the price history.
        
        Returns:
            TrackedProduct if successful, None if error.
        """
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if already tracking this product
            cursor.execute(
                "SELECT id, lowest_price, highest_price FROM tracked_products WHERE user_id = ? AND product_url = ?",
                (user_id, product_url)
            )
            existing = cursor.fetchone()
            
            if existing:
                product_id = existing["id"]
                lowest = existing["lowest_price"]
                highest = existing["highest_price"]
                
                # Update price bounds if we have a new price
                if initial_price is not None:
                    if lowest is None or initial_price < lowest:
                        lowest = initial_price
                    if highest is None or initial_price > highest:
                        highest = initial_price
                    
                    cursor.execute("""
                        UPDATE tracked_products 
                        SET current_price = ?, lowest_price = ?, highest_price = ?,
                            last_checked_at = ?, product_name = COALESCE(?, product_name),
                            retailer = COALESCE(?, retailer)
                        WHERE id = ?
                    """, (initial_price, lowest, highest, now, product_name, retailer, product_id))
                    
                    # Add price history point
                    cursor.execute("""
                        INSERT INTO price_history (product_id, price, net_price, best_cashback_rate, recorded_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (product_id, initial_price, net_price or initial_price, cashback_rate, now))
            else:
                # Create new tracked product
                cursor.execute("""
                    INSERT INTO tracked_products 
                    (user_id, product_url, product_name, retailer, current_price, 
                     lowest_price, highest_price, target_price, first_tracked_at, last_checked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, product_url, product_name, retailer, initial_price,
                    initial_price, initial_price, target_price, now, now
                ))
                product_id = cursor.lastrowid
                
                # Add initial price history point if we have a price
                if initial_price is not None:
                    cursor.execute("""
                        INSERT INTO price_history (product_id, price, net_price, best_cashback_rate, recorded_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (product_id, initial_price, net_price or initial_price, cashback_rate, now))
            
            conn.commit()
            
            return self.get_tracked_product(user_id, product_id)
    
    def get_tracked_product(self, user_id: int, product_id: int) -> Optional[TrackedProduct]:
        """Get a specific tracked product with its price history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tracked_products WHERE id = ? AND user_id = ?",
                (product_id, user_id)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            product = self._row_to_tracked_product(row)
            
            # Load price history
            cursor.execute("""
                SELECT * FROM price_history 
                WHERE product_id = ? 
                ORDER BY recorded_at ASC
            """, (product_id,))
            
            product.price_history = [
                self._row_to_price_point(r) for r in cursor.fetchall()
            ]
            
            return product
    
    def get_user_tracked_products(self, user_id: int, limit: int = 50) -> List[TrackedProduct]:
        """Get all products a user is tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tracked_products 
                WHERE user_id = ? 
                ORDER BY last_checked_at DESC 
                LIMIT ?
            """, (user_id, limit))
            
            products = []
            for row in cursor.fetchall():
                product = self._row_to_tracked_product(row)
                
                # Load minimal price history (last 30 days for charts)
                cursor.execute("""
                    SELECT * FROM price_history 
                    WHERE product_id = ? 
                    AND recorded_at >= datetime('now', '-30 days')
                    ORDER BY recorded_at ASC
                """, (product.id,))
                
                product.price_history = [
                    self._row_to_price_point(r) for r in cursor.fetchall()
                ]
                products.append(product)
            
            return products
    
    def get_product_price_history(
        self,
        product_id: int,
        days: int = 30
    ) -> List[PricePoint]:
        """Get price history for a specific product."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM price_history 
                WHERE product_id = ? 
                AND recorded_at >= datetime('now', ? || ' days')
                ORDER BY recorded_at ASC
            """, (product_id, -days))
            
            return [self._row_to_price_point(row) for row in cursor.fetchall()]
    
    def update_product_alert(
        self,
        user_id: int,
        product_id: int,
        target_price: Optional[float] = None,
        alert_enabled: bool = True
    ) -> bool:
        """Update price alert settings for a tracked product."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tracked_products 
                SET target_price = ?, alert_enabled = ?
                WHERE id = ? AND user_id = ?
            """, (target_price, alert_enabled, product_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def untrack_product(self, user_id: int, product_id: int) -> bool:
        """Stop tracking a product (deletes history)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM tracked_products WHERE id = ? AND user_id = ?",
                (product_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_products_with_price_drops(self, user_id: int) -> List[TrackedProduct]:
        """Get products that have dropped below their target price."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tracked_products 
                WHERE user_id = ? 
                AND alert_enabled = TRUE 
                AND target_price IS NOT NULL 
                AND current_price <= target_price
                ORDER BY (target_price - current_price) DESC
            """, (user_id,))
            
            return [self._row_to_tracked_product(row) for row in cursor.fetchall()]
    
    def get_price_tracking_stats(self, user_id: int) -> Dict[str, Any]:
        """Get aggregate price tracking stats for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Count tracked products
            cursor.execute(
                "SELECT COUNT(*) FROM tracked_products WHERE user_id = ?",
                (user_id,)
            )
            total_tracked = cursor.fetchone()[0]
            
            # Products with alerts
            cursor.execute(
                "SELECT COUNT(*) FROM tracked_products WHERE user_id = ? AND alert_enabled = TRUE",
                (user_id,)
            )
            with_alerts = cursor.fetchone()[0]
            
            # Products at lowest price
            cursor.execute("""
                SELECT COUNT(*) FROM tracked_products 
                WHERE user_id = ? AND current_price = lowest_price AND current_price IS NOT NULL
            """, (user_id,))
            at_lowest = cursor.fetchone()[0]
            
            # Total price observations
            cursor.execute("""
                SELECT COUNT(*) FROM price_history ph
                JOIN tracked_products tp ON ph.product_id = tp.id
                WHERE tp.user_id = ?
            """, (user_id,))
            total_observations = cursor.fetchone()[0]
            
            return {
                "total_tracked": total_tracked,
                "with_alerts": with_alerts,
                "at_lowest_price": at_lowest,
                "total_observations": total_observations,
            }
    
    @staticmethod
    def _row_to_tracked_product(row: sqlite3.Row) -> TrackedProduct:
        """Convert a database row to a TrackedProduct object."""
        return TrackedProduct(
            id=row["id"],
            user_id=row["user_id"],
            product_url=row["product_url"],
            product_name=row["product_name"],
            retailer=row["retailer"],
            current_price=row["current_price"],
            lowest_price=row["lowest_price"],
            highest_price=row["highest_price"],
            target_price=row["target_price"],
            alert_enabled=bool(row["alert_enabled"]),
            first_tracked_at=row["first_tracked_at"],
            last_checked_at=row["last_checked_at"],
        )
    
    @staticmethod
    def _row_to_price_point(row: sqlite3.Row) -> PricePoint:
        """Convert a database row to a PricePoint object."""
        return PricePoint(
            id=row["id"],
            product_id=row["product_id"],
            price=row["price"],
            net_price=row["net_price"],
            best_cashback_rate=row["best_cashback_rate"],
            recorded_at=row["recorded_at"],
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_db_instance: Optional[UserDatabase] = None


def get_user_database() -> UserDatabase:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = UserDatabase()
    return _db_instance


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Use local test database
    db = UserDatabase(db_path="./test_users.db")
    
    print("=== User Database Test ===\n")
    
    # Create test user
    print("Creating test user...")
    user = db.create_user("test@example.com", "password123")
    if user:
        print(f"✓ Created user: {user.email} (id={user.id})")
    else:
        print("✗ User already exists, fetching...")
        user = db.get_user_by_email("test@example.com")
    
    # Authenticate
    print("\nAuthenticating...")
    auth_user = db.authenticate_user("test@example.com", "password123")
    if auth_user:
        print(f"✓ Authenticated: {auth_user.email}")
    else:
        print("✗ Authentication failed")
    
    # Add cards to wallet
    print("\nAdding cards to wallet...")
    card1 = db.add_card_to_wallet(
        user.id,
        "chase_sapphire_preferred",
        "Sapphire Preferred",
        "Chase",
        base_rate=1.0,
        bonus_categories=[{"category": "dining", "rate": 3.0}]
    )
    if card1:
        print(f"✓ Added: {card1.name}")
    
    card2 = db.add_card_to_wallet(
        user.id,
        "citi_double_cash",
        "Double Cash",
        "Citi",
        base_rate=2.0
    )
    if card2:
        print(f"✓ Added: {card2.name}")
    
    # List wallet
    print("\nUser's wallet:")
    cards = db.get_user_cards(user.id)
    for card in cards:
        print(f"  - {card.issuer} {card.name}: {card.base_rate}% base")
    
    # Add search history
    print("\nAdding search history...")
    search = db.add_search_history(
        user.id,
        "https://amazon.com/dp/B123",
        product_price=99.99,
        net_price=85.50,
        product_name="Test Product",
        retailer="Amazon",
        total_savings=14.49,
        best_cashback_platform="Rakuten",
        best_cashback_rate=5.0
    )
    print(f"✓ Added search: {search.product_name}")
    
    # Show stats
    print("\nUser stats:")
    stats = db.get_user_savings_stats(user.id)
    print(f"  Total searches: {stats['total_searches']}")
    print(f"  Total saved: ${stats['total_saved']:.2f}")
    
    print("\n✓ All tests passed!")
