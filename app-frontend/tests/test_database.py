"""
Tests for the User Database module.
Tests user authentication, card wallet, and search history persistence.
"""

import os
import tempfile
import pytest
from datetime import datetime

# Add parent directory for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    UserDatabase,
    User, UserCard, SearchHistory,
    TrackedProduct, PricePoint,
    hash_password, verify_password,
    get_user_database,
)


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    database = UserDatabase(db_path=db_path)
    yield database
    
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


class TestPasswordHashing:
    """Test password hashing and verification."""
    
    def test_hash_password_returns_string(self):
        """Hash should return a string."""
        hashed = hash_password("test123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0
    
    def test_hash_password_different_for_same_input(self):
        """Two hashes of the same password should be different (due to salt)."""
        hash1 = hash_password("test123")
        hash2 = hash_password("test123")
        # With bcrypt, hashes should be different due to salt
        # With sha256+salt fallback, also different
        assert hash1 != hash2
    
    def test_verify_password_correct(self):
        """Correct password should verify."""
        password = "mySecurePassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
    
    def test_verify_password_wrong(self):
        """Wrong password should not verify."""
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False
    
    def test_verify_demo_password_with_demo_mode(self, monkeypatch):
        """Demo passwords should verify only when DEMO_MODE is enabled."""
        import database as db_module
        
        # Enable DEMO_MODE
        monkeypatch.setattr(db_module, 'DEMO_MODE', True)
        
        demo_hash = "$demo$admin123"
        assert verify_password("admin123", demo_hash) is True
        assert verify_password("wrong", demo_hash) is False
    
    def test_verify_demo_password_without_demo_mode(self, monkeypatch):
        """Demo passwords should fail when DEMO_MODE is disabled."""
        import database as db_module
        
        # Disable DEMO_MODE (production mode)
        monkeypatch.setattr(db_module, 'DEMO_MODE', False)
        
        demo_hash = "$demo$admin123"
        # Even correct password should fail when not in demo mode
        assert verify_password("admin123", demo_hash) is False
    
    def test_verify_password_malformed_sha256_hash(self):
        """Malformed SHA256 hash should fail safely."""
        # Missing parts
        assert verify_password("test", "$sha256$") is False
        assert verify_password("test", "$sha256$salt") is False
        assert verify_password("test", "$sha256$$") is False
        assert verify_password("test", "$sha256$salt$") is False
        assert verify_password("test", "") is False
        assert verify_password("test", None) is False  # None input
    
    def test_verify_password_malformed_bcrypt_hash(self):
        """Malformed bcrypt hash should fail safely."""
        # Too short
        assert verify_password("test", "$2a$") is False
        assert verify_password("test", "$2b$12$short") is False
        # Corrupted
        assert verify_password("test", "$2a$12$invalid!!characters!!here") is False
    
    def test_verify_password_unknown_format(self):
        """Unknown hash format should fail safely."""
        assert verify_password("test", "$unknown$format$hash") is False
        assert verify_password("test", "plaintext") is False
        assert verify_password("test", "12345") is False


class TestUserManagement:
    """Test user creation and authentication."""
    
    def test_create_user(self, db):
        """Create a new user."""
        user = db.create_user("test@example.com", "password123")
        
        assert user is not None
        assert user.email == "test@example.com"
        assert user.id > 0
        assert user.is_admin is False
    
    def test_create_admin_user(self, db):
        """Create an admin user."""
        user = db.create_user("admin@example.com", "adminpass", is_admin=True)
        
        assert user is not None
        assert user.is_admin is True
    
    def test_create_duplicate_user(self, db):
        """Duplicate email should return None."""
        db.create_user("dup@example.com", "pass1")
        result = db.create_user("dup@example.com", "pass2")
        
        assert result is None
    
    def test_create_user_case_insensitive_email(self, db):
        """Email should be case-insensitive."""
        db.create_user("Test@Example.COM", "pass")
        result = db.create_user("test@example.com", "pass2")
        
        assert result is None  # Should be duplicate
    
    def test_get_user_by_email(self, db):
        """Retrieve user by email."""
        db.create_user("find@example.com", "pass")
        
        user = db.get_user_by_email("find@example.com")
        assert user is not None
        assert user.email == "find@example.com"
    
    def test_get_user_by_email_not_found(self, db):
        """Non-existent user should return None."""
        user = db.get_user_by_email("nobody@example.com")
        assert user is None
    
    def test_get_user_by_id(self, db):
        """Retrieve user by ID."""
        created = db.create_user("byid@example.com", "pass")
        
        user = db.get_user_by_id(created.id)
        assert user is not None
        assert user.email == "byid@example.com"
    
    def test_authenticate_user_success(self, db):
        """Successful authentication."""
        db.create_user("auth@example.com", "correctpass")
        
        user = db.authenticate_user("auth@example.com", "correctpass")
        assert user is not None
        assert user.email == "auth@example.com"
    
    def test_authenticate_user_wrong_password(self, db):
        """Wrong password should fail."""
        db.create_user("auth2@example.com", "correctpass")
        
        user = db.authenticate_user("auth2@example.com", "wrongpass")
        assert user is None
    
    def test_authenticate_user_not_found(self, db):
        """Non-existent user should fail."""
        user = db.authenticate_user("nobody@example.com", "pass")
        assert user is None
    
    def test_get_all_users(self, db):
        """Get all users."""
        db.create_user("user1@example.com", "pass")
        db.create_user("user2@example.com", "pass")
        db.create_user("user3@example.com", "pass")
        
        users = db.get_all_users()
        assert len(users) == 3
    
    def test_get_user_count(self, db):
        """Count all users."""
        assert db.get_user_count() == 0
        
        db.create_user("u1@example.com", "pass")
        assert db.get_user_count() == 1
        
        db.create_user("u2@example.com", "pass")
        assert db.get_user_count() == 2
    
    def test_update_user_settings(self, db):
        """Update user settings."""
        user = db.create_user("settings@example.com", "pass")
        
        db.update_user_settings(user.id, tax_rate=8.25, location="California")
        
        updated = db.get_user_by_id(user.id)
        assert updated.tax_rate == 8.25
        assert updated.location == "California"


class TestCardWallet:
    """Test credit card wallet management."""
    
    def test_add_card_to_wallet(self, db):
        """Add a card to user's wallet."""
        user = db.create_user("cards@example.com", "pass")
        
        card = db.add_card_to_wallet(
            user_id=user.id,
            card_id="chase_sapphire",
            name="Sapphire Preferred",
            issuer="Chase",
            base_rate=1.0,
            bonus_categories=[{"category": "dining", "rate": 3.0}]
        )
        
        assert card is not None
        assert card.name == "Sapphire Preferred"
        assert card.issuer == "Chase"
    
    def test_add_duplicate_card(self, db):
        """Adding same card twice should fail."""
        user = db.create_user("dup_card@example.com", "pass")
        
        db.add_card_to_wallet(user.id, "chase_sapphire", "Sapphire", "Chase", 1.0)
        result = db.add_card_to_wallet(user.id, "chase_sapphire", "Sapphire", "Chase", 1.0)
        
        assert result is None
    
    def test_get_user_cards(self, db):
        """Get all cards in wallet."""
        user = db.create_user("wallet@example.com", "pass")
        
        db.add_card_to_wallet(user.id, "card1", "Card 1", "Issuer1", 1.0)
        db.add_card_to_wallet(user.id, "card2", "Card 2", "Issuer2", 2.0)
        
        cards = db.get_user_cards(user.id)
        assert len(cards) == 2
    
    def test_remove_card_from_wallet(self, db):
        """Remove a card from wallet."""
        user = db.create_user("remove@example.com", "pass")
        db.add_card_to_wallet(user.id, "to_remove", "Card", "Issuer", 1.0)
        
        result = db.remove_card_from_wallet(user.id, "to_remove")
        assert result is True
        
        cards = db.get_user_cards(user.id)
        assert len(cards) == 0
    
    def test_remove_nonexistent_card(self, db):
        """Removing non-existent card should return False."""
        user = db.create_user("no_remove@example.com", "pass")
        result = db.remove_card_from_wallet(user.id, "nonexistent")
        assert result is False
    
    def test_clear_user_wallet(self, db):
        """Clear all cards from wallet."""
        user = db.create_user("clear@example.com", "pass")
        db.add_card_to_wallet(user.id, "card1", "Card 1", "Issuer1", 1.0)
        db.add_card_to_wallet(user.id, "card2", "Card 2", "Issuer2", 2.0)
        
        count = db.clear_user_wallet(user.id)
        assert count == 2
        
        cards = db.get_user_cards(user.id)
        assert len(cards) == 0
    
    def test_card_bonus_categories_json(self, db):
        """Bonus categories should be stored and retrieved as JSON."""
        user = db.create_user("bonus@example.com", "pass")
        
        bonus = [
            {"category": "dining", "rate": 3.0},
            {"category": "travel", "rate": 2.0}
        ]
        db.add_card_to_wallet(user.id, "bonus_card", "Card", "Issuer", 1.0, bonus_categories=bonus)
        
        cards = db.get_user_cards(user.id)
        assert cards[0].bonus_categories == bonus


class TestSearchHistory:
    """Test search history storage."""
    
    def test_add_search_history(self, db):
        """Add a search to history."""
        user = db.create_user("search@example.com", "pass")
        
        search = db.add_search_history(
            user_id=user.id,
            product_url="https://amazon.com/product/123",
            product_price=99.99,
            net_price=85.50,
            product_name="Test Product",
            retailer="Amazon",
            total_savings=14.49,
            best_cashback_platform="Rakuten",
            best_cashback_rate=5.0
        )
        
        assert search is not None
        assert search.product_name == "Test Product"
        assert search.total_savings == 14.49
    
    def test_get_user_search_history(self, db):
        """Get user's search history."""
        user = db.create_user("history@example.com", "pass")
        
        db.add_search_history(user.id, "url1", 100, 90)
        db.add_search_history(user.id, "url2", 200, 180)
        db.add_search_history(user.id, "url3", 300, 270)
        
        history = db.get_user_search_history(user.id)
        assert len(history) == 3
    
    def test_search_history_limit(self, db):
        """Limit should work correctly."""
        user = db.create_user("limit@example.com", "pass")
        
        for i in range(10):
            db.add_search_history(user.id, f"url{i}", 100, 90)
        
        history = db.get_user_search_history(user.id, limit=5)
        assert len(history) == 5
    
    def test_get_total_searches(self, db):
        """Get total search count."""
        user1 = db.create_user("total1@example.com", "pass")
        user2 = db.create_user("total2@example.com", "pass")
        
        db.add_search_history(user1.id, "url1", 100, 90)
        db.add_search_history(user1.id, "url2", 100, 90)
        db.add_search_history(user2.id, "url3", 100, 90)
        
        total = db.get_total_searches()
        assert total == 3
    
    def test_get_top_retailers(self, db):
        """Get most searched retailers."""
        user = db.create_user("top@example.com", "pass")
        
        db.add_search_history(user.id, "url1", 100, 90, retailer="Amazon")
        db.add_search_history(user.id, "url2", 100, 90, retailer="Amazon")
        db.add_search_history(user.id, "url3", 100, 90, retailer="Amazon")
        db.add_search_history(user.id, "url4", 100, 90, retailer="BestBuy")
        db.add_search_history(user.id, "url5", 100, 90, retailer="BestBuy")
        db.add_search_history(user.id, "url6", 100, 90, retailer="Target")
        
        top = db.get_top_retailers(limit=2)
        assert len(top) == 2
        assert top[0]["retailer"] == "Amazon"
        assert top[0]["count"] == 3
    
    def test_get_user_savings_stats(self, db):
        """Get aggregate savings stats."""
        user = db.create_user("stats@example.com", "pass")
        
        db.add_search_history(user.id, "url1", 100, 90, total_savings=10)
        db.add_search_history(user.id, "url2", 200, 180, total_savings=20)
        db.add_search_history(user.id, "url3", 300, 250, total_savings=50)
        
        stats = db.get_user_savings_stats(user.id)
        assert stats["total_searches"] == 3
        assert stats["total_saved"] == 80
        assert stats["best_savings"] == 50
    
    def test_get_user_savings_stats_empty_history(self, db):
        """Stats for user with no history should return zeros safely."""
        user = db.create_user("empty_stats@example.com", "pass")
        
        # No search history added - should return safe defaults
        stats = db.get_user_savings_stats(user.id)
        assert stats["total_searches"] == 0
        assert stats["total_saved"] == 0.0
        assert stats["best_savings"] == 0.0
    
    def test_get_user_savings_stats_nonexistent_user(self, db):
        """Stats for non-existent user should return zeros safely."""
        # User ID 9999 doesn't exist
        stats = db.get_user_savings_stats(9999)
        assert stats["total_searches"] == 0
        assert stats["total_saved"] == 0.0
        assert stats["best_savings"] == 0.0


class TestDatabasePersistence:
    """Test that data persists across database reconnections."""
    
    def test_user_persists(self):
        """User should persist after database reconnect."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Create user
            db1 = UserDatabase(db_path=db_path)
            db1.create_user("persist@example.com", "password")
            del db1
            
            # Reconnect and verify
            db2 = UserDatabase(db_path=db_path)
            user = db2.get_user_by_email("persist@example.com")
            assert user is not None
            assert user.email == "persist@example.com"
            
            # Should still be able to authenticate
            auth_user = db2.authenticate_user("persist@example.com", "password")
            assert auth_user is not None
        finally:
            os.unlink(db_path)
    
    def test_cards_persist(self):
        """Cards should persist after database reconnect."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Create user and add cards
            db1 = UserDatabase(db_path=db_path)
            user = db1.create_user("cards_persist@example.com", "password")
            db1.add_card_to_wallet(user.id, "chase_sapphire", "Sapphire", "Chase", 1.0)
            db1.add_card_to_wallet(user.id, "amex_gold", "Gold", "Amex", 1.0)
            del db1
            
            # Reconnect and verify
            db2 = UserDatabase(db_path=db_path)
            user = db2.get_user_by_email("cards_persist@example.com")
            cards = db2.get_user_cards(user.id)
            assert len(cards) == 2
        finally:
            os.unlink(db_path)


class TestSingleton:
    """Test singleton behavior of get_user_database."""
    
    def test_get_user_database_singleton_returns_same_instance(self, monkeypatch):
        """Singleton should return the same instance on repeated calls."""
        import database as db_module
        
        # Reset singleton for clean test
        monkeypatch.setattr(db_module, '_db_instance', None)
        
        # Use temp file for test
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            monkeypatch.setenv("USER_DB_PATH", db_path)
            # Force re-evaluation of default path
            monkeypatch.setattr(db_module, 'DEFAULT_DB_PATH', db_path)
            
            db1 = get_user_database()
            db2 = get_user_database()
            
            assert db1 is db2, "Singleton should return the same instance"
        finally:
            os.unlink(db_path)
    
    def test_get_user_database_uses_env_path(self, monkeypatch):
        """Singleton should use USER_DB_PATH environment variable."""
        import database as db_module
        
        # Reset singleton for clean test
        monkeypatch.setattr(db_module, '_db_instance', None)
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            custom_path = f.name
        
        try:
            # Set custom path via environment variable
            monkeypatch.setenv("USER_DB_PATH", custom_path)
            
            db = UserDatabase()  # Uses env var
            assert db.db_path == custom_path
            
            # Verify it actually creates the database at that path
            assert os.path.exists(custom_path)
        finally:
            os.unlink(custom_path)


class TestPriceTracking:
    """Test price tracking and history functionality."""
    
    def test_track_product_new(self, db):
        """Track a new product."""
        user = db.register_user("tracker@example.com", "password123", "Tracker")
        
        product = db.track_product(
            user_id=user.id,
            product_url="https://amazon.com/product/123",
            product_name="Test Product",
            retailer="amazon",
            initial_price=99.99,
            net_price=89.99,
            cashback_rate=5.0
        )
        
        assert product is not None
        assert product.product_url == "https://amazon.com/product/123"
        assert product.product_name == "Test Product"
        assert product.current_price == 99.99
        assert product.lowest_price == 99.99
        assert product.highest_price == 99.99
    
    def test_track_product_price_update(self, db):
        """Track product with price change updates history."""
        user = db.register_user("tracker2@example.com", "password123", "Tracker2")
        
        # Initial price
        db.track_product(
            user_id=user.id,
            product_url="https://amazon.com/product/456",
            product_name="Price Drop Product",
            retailer="amazon",
            initial_price=100.00,
            net_price=90.00,
            cashback_rate=5.0
        )
        
        # Price drop
        product = db.track_product(
            user_id=user.id,
            product_url="https://amazon.com/product/456",
            product_name="Price Drop Product",
            retailer="amazon",
            initial_price=80.00,  # Lower price
            net_price=72.00,
            cashback_rate=5.0
        )
        
        assert product.current_price == 80.00
        assert product.lowest_price == 80.00
        assert product.highest_price == 100.00
        assert len(product.price_history) == 2
    
    def test_get_tracked_product(self, db):
        """Get a single tracked product with history."""
        user = db.register_user("getter@example.com", "password123", "Getter")
        
        db.track_product(
            user_id=user.id,
            product_url="https://walmart.com/product/789",
            product_name="Getter Product",
            retailer="walmart",
            initial_price=50.00,
            net_price=47.50,
            cashback_rate=2.5
        )
        
        product = db.get_tracked_product(user.id, "https://walmart.com/product/789")
        
        assert product is not None
        assert product.product_name == "Getter Product"
        assert product.retailer == "walmart"
    
    def test_get_tracked_product_not_found(self, db):
        """Get nonexistent product returns None."""
        user = db.register_user("notfound@example.com", "password123", "NotFound")
        
        product = db.get_tracked_product(user.id, "https://nonexistent.com/product")
        assert product is None
    
    def test_get_user_tracked_products(self, db):
        """Get all tracked products for a user."""
        user = db.register_user("multi@example.com", "password123", "Multi")
        
        # Track multiple products
        for i in range(3):
            db.track_product(
                user_id=user.id,
                product_url=f"https://store.com/product/{i}",
                product_name=f"Product {i}",
                retailer="store",
                initial_price=10.00 * (i + 1),
                net_price=9.00 * (i + 1),
                cashback_rate=5.0
            )
        
        products = db.get_user_tracked_products(user.id)
        assert len(products) == 3
    
    def test_get_product_price_history(self, db):
        """Get price history for a product."""
        user = db.register_user("history@example.com", "password123", "History")
        
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/history-product",
            product_name="History Product",
            retailer="store",
            initial_price=100.00,
            net_price=90.00,
            cashback_rate=5.0
        )
        
        # Add more price points
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/history-product",
            product_name="History Product",
            retailer="store",
            initial_price=95.00,
            net_price=85.50,
            cashback_rate=5.0
        )
        
        history = db.get_product_price_history(user.id, "https://store.com/history-product")
        assert len(history) == 2
        assert all(isinstance(p, PricePoint) for p in history)
    
    def test_update_product_alert(self, db):
        """Update product price alert settings."""
        user = db.register_user("alert@example.com", "password123", "Alert")
        
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/alert-product",
            product_name="Alert Product",
            retailer="store",
            initial_price=100.00,
            net_price=90.00,
            cashback_rate=5.0
        )
        
        success = db.update_product_alert(
            user_id=user.id,
            product_url="https://store.com/alert-product",
            target_price=75.00,
            alert_enabled=True
        )
        
        assert success is True
        
        product = db.get_tracked_product(user.id, "https://store.com/alert-product")
        assert product.target_price == 75.00
        assert product.alert_enabled is True
    
    def test_untrack_product(self, db):
        """Untrack a product."""
        user = db.register_user("untrack@example.com", "password123", "Untrack")
        
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/untrack-product",
            product_name="Untrack Product",
            retailer="store",
            initial_price=50.00,
            net_price=45.00,
            cashback_rate=5.0
        )
        
        success = db.untrack_product(user.id, "https://store.com/untrack-product")
        assert success is True
        
        product = db.get_tracked_product(user.id, "https://store.com/untrack-product")
        assert product is None
    
    def test_get_products_with_price_drops(self, db):
        """Get products that dropped below target price."""
        user = db.register_user("drops@example.com", "password123", "Drops")
        
        # Product at target
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/drop-product",
            product_name="Drop Product",
            retailer="store",
            initial_price=100.00,
            net_price=90.00,
            cashback_rate=5.0
        )
        
        db.update_product_alert(
            user_id=user.id,
            product_url="https://store.com/drop-product",
            target_price=90.00,
            alert_enabled=True
        )
        
        # Simulate price drop
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/drop-product",
            product_name="Drop Product",
            retailer="store",
            initial_price=80.00,  # Below target
            net_price=72.00,
            cashback_rate=5.0
        )
        
        drops = db.get_products_with_price_drops(user.id)
        assert len(drops) >= 1
        assert any(p.product_url == "https://store.com/drop-product" for p in drops)
    
    def test_get_price_tracking_stats(self, db):
        """Get aggregate price tracking stats for a user."""
        user = db.register_user("stats@example.com", "password123", "Stats")
        
        # Track a few products
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/stats-1",
            product_name="Stats Product 1",
            retailer="store",
            initial_price=100.00,
            net_price=90.00,
            cashback_rate=5.0
        )
        
        db.track_product(
            user_id=user.id,
            product_url="https://store.com/stats-2",
            product_name="Stats Product 2",
            retailer="store",
            initial_price=50.00,
            net_price=45.00,
            cashback_rate=5.0
        )
        
        stats = db.get_price_tracking_stats(user.id)
        
        assert stats["total_tracked"] == 2
        assert "products_at_lowest" in stats
        assert "products_with_alerts" in stats


class TestTrackedProductDataclass:
    """Test TrackedProduct dataclass methods."""
    
    def test_calculate_drop_percent(self):
        """Test price drop percentage calculation."""
        product = TrackedProduct(
            id=1,
            user_id=1,
            product_url="https://example.com/product",
            product_name="Test",
            retailer="test",
            current_price=80.00,
            lowest_price=80.00,
            highest_price=100.00,
            first_tracked_at="2024-01-01",
            last_checked_at="2024-01-15"
        )
        
        drop = product._calculate_drop_percent()
        assert drop == 20.0  # 20% drop from 100 to 80
    
    def test_calculate_drop_percent_no_drop(self):
        """Test when current equals highest."""
        product = TrackedProduct(
            id=1,
            user_id=1,
            product_url="https://example.com/product",
            product_name="Test",
            retailer="test",
            current_price=100.00,
            lowest_price=100.00,
            highest_price=100.00,
            first_tracked_at="2024-01-01",
            last_checked_at="2024-01-15"
        )
        
        drop = product._calculate_drop_percent()
        assert drop == 0.0
    
    def test_to_dict(self):
        """Test TrackedProduct serialization."""
        product = TrackedProduct(
            id=1,
            user_id=1,
            product_url="https://example.com/product",
            product_name="Test Product",
            retailer="amazon",
            current_price=89.99,
            lowest_price=79.99,
            highest_price=99.99,
            target_price=70.00,
            alert_enabled=True,
            first_tracked_at="2024-01-01",
            last_checked_at="2024-01-15"
        )
        
        data = product.to_dict()
        
        assert data["product_url"] == "https://example.com/product"
        assert data["current_price"] == 89.99
        assert data["lowest_price"] == 79.99
        assert data["highest_price"] == 99.99
        assert data["price_drop_percent"] is not None


class TestPricePointDataclass:
    """Test PricePoint dataclass methods."""
    
    def test_to_dict(self):
        """Test PricePoint serialization."""
        point = PricePoint(
            id=1,
            product_id=1,
            price=99.99,
            net_price=89.99,
            best_cashback_rate=5.0,
            recorded_at="2024-01-15T12:00:00"
        )
        
        data = point.to_dict()
        
        assert data["price"] == 99.99
        assert data["net_price"] == 89.99
        assert data["best_cashback_rate"] == 5.0
        assert data["recorded_at"] == "2024-01-15T12:00:00"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
