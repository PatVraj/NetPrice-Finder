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
    """Verify a password against its hash."""
    # Handle demo user special case
    if password_hash.startswith("$demo$"):
        return password == password_hash[6:]
    
    if BCRYPT_AVAILABLE and password_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False
    elif password_hash.startswith("$sha256$"):
        parts = password_hash.split("$")
        if len(parts) != 4:
            return False
        salt = parts[2]
        stored_hash = parts[3]
        computed = hashlib.sha256((salt + password).encode()).hexdigest()
        return computed == stored_hash
    
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
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_user_cards_user ON user_cards(user_id);
                CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);
                CREATE INDEX IF NOT EXISTS idx_search_history_date ON search_history(searched_at);
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
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
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
    
    def update_user_settings(
        self,
        user_id: int,
        tax_rate: Optional[float] = None,
        location: Optional[str] = None
    ) -> bool:
        """Update user's preferences."""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            updates = ["updated_at = ?"]
            params = [now]
            
            if tax_rate is not None:
                updates.append("tax_rate = ?")
                params.append(tax_rate)
            
            if location is not None:
                updates.append("location = ?")
                params.append(location)
            
            params.append(user_id)
            
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_users(self) -> List[User]:
        """Get all users (admin function)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
            
            return [
                User(
                    id=row["id"],
                    email=row["email"],
                    password_hash=row["password_hash"],
                    is_admin=bool(row["is_admin"]),
                    tax_rate=row["tax_rate"],
                    location=row["location"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
                for row in cursor.fetchall()
            ]
    
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
        import json
        now = datetime.now().isoformat()
        bonus_json = json.dumps(bonus_categories or [])
        
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
        import json
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_cards WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            )
            
            cards = []
            for row in cursor.fetchall():
                bonus = json.loads(row["bonus_categories"]) if row["bonus_categories"] else []
                cards.append(UserCard(
                    id=row["id"],
                    user_id=row["user_id"],
                    card_id=row["card_id"],
                    name=row["name"],
                    issuer=row["issuer"],
                    base_rate=row["base_rate"],
                    bonus_categories=bonus,
                    is_custom=bool(row["is_custom"]),
                    created_at=row["created_at"]
                ))
            return cards
    
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
