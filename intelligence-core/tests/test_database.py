"""
Test Suite: Retailer Database

Tests for the SQLite database layer.
Run: pytest tests/test_database.py -v
"""

import pytest
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from retailer.database import RetailerDatabase
from retailer.models import (
    Retailer,
    RetailerTier,
    StoredCashbackOffer,
    normalize_retailer_name,
    is_major_retailer,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    db = RetailerDatabase(db_path)
    yield db
    
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


class TestRetailerDatabaseInit:
    """Test database initialization."""

    def test_creates_database_file(self, temp_db):
        """Test that database file is created."""
        assert Path(temp_db.db_path).exists()

    def test_schema_initialized(self, temp_db):
        """Test that schema tables are created."""
        with temp_db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check key tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='retailers'
            """)
            assert cursor.fetchone() is not None
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='cashback_offers'
            """)
            assert cursor.fetchone() is not None


class TestRetailerCRUD:
    """Test retailer create/read operations."""

    def test_get_or_create_retailer(self, temp_db):
        """Test creating a new retailer."""
        retailer = temp_db.get_or_create_retailer("Nike")
        
        assert retailer is not None
        assert retailer.name == "Nike"
        assert retailer.normalized_name == "nike"

    def test_get_existing_retailer(self, temp_db):
        """Test retrieving an existing retailer."""
        # Create first
        temp_db.get_or_create_retailer("Nike")
        
        # Get again - should return same record
        retailer = temp_db.get_or_create_retailer("Nike")
        
        assert retailer.name == "Nike"

    def test_get_retailer_by_name(self, temp_db):
        """Test getting retailer by name."""
        temp_db.get_or_create_retailer("Amazon")
        
        retailer = temp_db.get_retailer_by_name("amazon")
        
        assert retailer is not None
        assert retailer.name == "Amazon"

    def test_get_nonexistent_retailer(self, temp_db):
        """Test getting a retailer that doesn't exist."""
        retailer = temp_db.get_retailer_by_name("NonExistentStore12345")
        
        assert retailer is None

    def test_retailer_normalization(self, temp_db):
        """Test that retailer names are normalized."""
        temp_db.get_or_create_retailer("  NIKE  ")
        
        # Should find with different casing
        retailer = temp_db.get_retailer_by_name("nike")
        
        assert retailer is not None


class TestCashbackOffers:
    """Test cashback offer storage."""

    def test_save_cashback_offers(self, temp_db):
        """Test saving cashback offers."""
        retailer = temp_db.get_or_create_retailer("Nike")
        
        offer = StoredCashbackOffer(
            retailer_id=retailer.id,
            platform="rakuten",
            cashback_percent=6.0,
            terms="Standard terms",
            affiliate_url="https://rakuten.com/nike",
        )
        
        temp_db.save_cashback_offers(retailer.id, "rakuten", [offer])
        
        # Verify it was added
        offers = temp_db.get_cashback_offers(retailer.id)
        assert len(offers) >= 1
        assert any(o.platform == "rakuten" for o in offers)

    def test_get_cashback_offers_empty(self, temp_db):
        """Test getting offers for retailer with none."""
        retailer = temp_db.get_or_create_retailer("TestStore")
        
        offers = temp_db.get_cashback_offers(retailer.id)
        
        assert offers == []

    def test_get_cashback_offers_by_platform(self, temp_db):
        """Test filtering offers by platform."""
        retailer = temp_db.get_or_create_retailer("Nike")
        
        # Add offers from different platforms
        for platform, rate in [("rakuten", 6.0), ("topcashback", 5.0), ("honey", 4.0)]:
            offer = StoredCashbackOffer(
                retailer_id=retailer.id,
                platform=platform,
                cashback_percent=rate,
            )
            temp_db.save_cashback_offers(retailer.id, platform, [offer])
        
        # Filter by platform
        rakuten_offers = temp_db.get_cashback_offers(retailer.id, platform="rakuten")
        
        assert len(rakuten_offers) >= 1
        assert all(o.platform == "rakuten" for o in rakuten_offers)


class TestDatabaseStats:
    """Test database statistics functions."""

    def test_get_stats_empty(self, temp_db):
        """Test stats on empty database."""
        stats = temp_db.get_stats()
        
        assert "total_retailers" in stats
        assert "total_cashback_offers" in stats
        assert "platforms_tracked" in stats
        assert stats["total_retailers"] == 0

    def test_get_stats_with_data(self, temp_db):
        """Test stats with data."""
        # Add some retailers
        temp_db.get_or_create_retailer("Nike")
        temp_db.get_or_create_retailer("Amazon")
        temp_db.get_or_create_retailer("Target")
        
        stats = temp_db.get_stats()
        
        assert stats["total_retailers"] == 3

    def test_get_top_retailers_empty(self, temp_db):
        """Test top retailers on empty database."""
        result = temp_db.get_top_retailers(limit=5)
        
        assert isinstance(result, list)

    def test_get_top_retailers_with_data(self, temp_db):
        """Test top retailers with data."""
        # Add retailers
        temp_db.get_or_create_retailer("Nike")
        temp_db.get_or_create_retailer("Amazon")
        
        result = temp_db.get_top_retailers(limit=10)
        
        assert isinstance(result, list)
        # Should have the retailers we added
        if result:
            assert "name" in result[0]
            assert "rank" in result[0]

    def test_get_platform_status_empty(self, temp_db):
        """Test platform status on empty database."""
        result = temp_db.get_platform_status()
        
        assert isinstance(result, list)

    def test_get_platform_status_structure(self, temp_db):
        """Test platform status response structure."""
        result = temp_db.get_platform_status()
        
        # Even if empty, should return a list
        assert isinstance(result, list)
        
        # If there's data, check structure
        if result:
            platform = result[0]
            assert "name" in platform
            assert "active" in platform
            assert "success_rate" in platform


class TestRetailerModels:
    """Test retailer model utilities."""

    def test_normalize_retailer_name(self):
        """Test retailer name normalization."""
        assert normalize_retailer_name("  Nike  ") == "nike"
        assert normalize_retailer_name("AMAZON") == "amazon"
        assert normalize_retailer_name("Best Buy") == "best buy"

    def test_is_major_retailer(self):
        """Test major retailer detection."""
        # These should be major retailers
        assert is_major_retailer("Amazon") == True
        assert is_major_retailer("walmart") == True
        assert is_major_retailer("Target") == True
        
        # This probably isn't
        assert is_major_retailer("RandomSmallShop123") == False


class TestDatabaseCleanup:
    """Test database cleanup operations."""

    def test_cleanup_old_data(self, temp_db):
        """Test that cleanup doesn't error on empty database."""
        # Should not raise
        temp_db.cleanup_old_data(days_old=30)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
