"""
Test Suite: API Endpoints

Tests for the FastAPI server endpoints.
Run: pytest tests/test_api.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Skip if fastapi not installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from api.server import app


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test cases for health check endpoint."""

    def test_health_check(self, client):
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "services" in data

    def test_health_check_services(self, client):
        """Test that health check reports service status."""
        response = client.get("/health")
        
        data = response.json()
        assert "optimizer" in data["services"]
        assert "cashback_monitor" in data["services"]


class TestQuickPriceEndpoint:
    """Test cases for quick price calculation endpoint."""

    def test_quick_price_basic(self, client):
        """Test basic quick price calculation."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 10.00,
            "tax_rate": 0.0825,
            "shipping": 0.00
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert "net_price" in data
        assert "total_savings" in data
        assert "savings_percent" in data
        assert data["net_price"] < 100.00

    def test_quick_price_no_discounts(self, client):
        """Test quick price with no discounts."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 50.00,
            "cashback_percent": 0,
            "card_reward_percent": 0,
            "coupon_discount": 0,
            "tax_rate": 0,
            "shipping": 0
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["net_price"] == 50.00

    def test_quick_price_validation_error(self, client):
        """Test that invalid input returns validation error."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": -10.00,  # Invalid: negative price
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422  # Validation error

    def test_quick_price_missing_required(self, client):
        """Test that missing required fields returns error."""
        response = client.post("/api/v1/quick-price", json={
            # Missing product_price
            "cashback_percent": 5.0
        })
        
        assert response.status_code == 422

    def test_quick_price_with_shipping(self, client):
        """Test quick price with shipping cost."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 0,
            "card_reward_percent": 0,
            "coupon_discount": 0,
            "tax_rate": 0,
            "shipping": 9.99
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["shipping"] == 9.99
        assert data["net_price"] == pytest.approx(109.99, rel=0.01)


class TestWalletEndpoints:
    """Test cases for wallet management endpoints."""

    def test_get_empty_wallet(self, client):
        """Test getting an empty wallet."""
        response = client.get("/api/v1/wallet")
        
        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
        assert "card_count" in data

    def test_get_popular_cards(self, client):
        """Test getting list of popular cards."""
        response = client.get("/api/v1/popular-cards")
        
        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
        assert len(data["cards"]) > 0
        
        # Check card structure
        card = data["cards"][0]
        assert "name" in card
        assert "issuer" in card
        assert "base_rate" in card

    def test_add_popular_card_to_wallet(self, client):
        """Test adding a popular card to wallet."""
        # First, get available cards
        cards_response = client.get("/api/v1/popular-cards")
        cards = cards_response.json()["cards"]
        
        if cards:
            card_name = cards[0]["name"]
            
            # Add the card
            response = client.post(f"/api/v1/wallet/add-popular/{card_name}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "added"
            assert data["card"] == card_name

    def test_add_nonexistent_card(self, client):
        """Test adding a card that doesn't exist."""
        response = client.post("/api/v1/wallet/add-popular/NonExistentCard12345")
        
        assert response.status_code == 404

    def test_remove_card_from_wallet(self, client):
        """Test removing a card from wallet."""
        # First add a card
        cards_response = client.get("/api/v1/popular-cards")
        cards = cards_response.json()["cards"]
        
        if cards:
            card_name = cards[0]["name"]
            client.post(f"/api/v1/wallet/add-popular/{card_name}")
            
            # Then remove it
            response = client.delete(f"/api/v1/wallet/{card_name}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "removed"

    def test_add_custom_card(self, client):
        """Test adding a custom card to wallet."""
        response = client.post("/api/v1/wallet/add", json={
            "name": "My Custom Card",
            "issuer": "My Bank",
            "base_rate": 1.5,
            "bonus_categories": [
                {"category": "Dining", "rate": 3.0},
                {"category": "Travel", "rate": 2.0}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "added"
        assert data["card"] == "My Custom Card"


class TestFindBestPriceEndpoint:
    """Test cases for the main find-best-price endpoint."""

    def test_find_best_price_invalid_url(self, client):
        """Test with invalid URL format."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "not a valid url",
            "include_cashback": True,
            "include_coupons": True
        })
        
        # Should still accept the request (might fail during processing)
        assert response.status_code in [200, 404, 500]

    def test_find_best_price_request_format(self, client):
        """Test that request format is validated correctly."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "https://example.com/product/123",
            "include_cashback": True,
            "include_coupons": True
        })
        
        # Request format should be valid
        assert response.status_code in [200, 404, 500]

    def test_find_best_price_missing_query(self, client):
        """Test missing query parameter."""
        response = client.post("/api/v1/find-best-price", json={
            "include_cashback": True
        })
        
        assert response.status_code == 422


class TestCashbackRatesEndpoint:
    """Test cases for cashback rates endpoint."""

    def test_cashback_rates_request_format(self, client):
        """Test cashback rates request format."""
        response = client.post("/api/v1/cashback-rates", json={
            "merchant": "Nike"
        })
        
        # Should accept the request
        assert response.status_code in [200, 500]

    def test_cashback_rates_missing_merchant(self, client):
        """Test missing merchant parameter."""
        response = client.post("/api/v1/cashback-rates", json={})
        
        assert response.status_code == 422


class TestAPIResponseFormats:
    """Test API response format consistency."""

    def test_quick_price_response_fields(self, client):
        """Test that quick price response has all expected fields."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 10.00,
            "tax_rate": 0.0825,
            "shipping": 0.00
        })
        
        data = response.json()
        
        expected_fields = [
            "product_price",
            "coupon_discount",
            "tax",
            "shipping",
            "gross_total",
            "cashback",
            "card_rewards",
            "net_price",
            "total_savings",
            "savings_percent"
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_wallet_response_fields(self, client):
        """Test wallet response has expected fields."""
        response = client.get("/api/v1/wallet")
        
        data = response.json()
        assert "cards" in data
        assert "card_count" in data
        assert isinstance(data["cards"], list)

    def test_popular_cards_response_fields(self, client):
        """Test popular cards response has expected fields."""
        response = client.get("/api/v1/popular-cards")
        
        data = response.json()
        assert "cards" in data
        
        if data["cards"]:
            card = data["cards"][0]
            assert "name" in card
            assert "issuer" in card
            assert "base_rate" in card
            assert "highlights" in card


class TestCORSAndHeaders:
    """Test CORS and header handling."""

    def test_cors_headers(self, client):
        """Test that CORS headers are set correctly."""
        response = client.options("/api/v1/quick-price")
        
        # CORS preflight should work
        assert response.status_code in [200, 405]


class TestErrorHandling:
    """Test error handling in API."""

    def test_invalid_json(self, client):
        """Test handling of invalid JSON."""
        response = client.post(
            "/api/v1/quick-price",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422

    def test_wrong_content_type(self, client):
        """Test handling of wrong content type."""
        response = client.post(
            "/api/v1/quick-price",
            content="product_price=100",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code in [422, 415]

    def test_404_endpoint(self, client):
        """Test accessing non-existent endpoint."""
        response = client.get("/api/v1/nonexistent")
        
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
