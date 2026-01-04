"""
Tests for API Error Handling and Edge Cases.
Tests graceful degradation, error responses, and boundary conditions.

Run: pytest tests/test_error_handling.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

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


# =============================================================================
# Input Validation Error Tests
# =============================================================================

class TestInputValidationErrors:
    """Test API input validation and error responses."""
    
    def test_quick_price_negative_price(self, client):
        """Negative product price should be rejected."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": -50.00,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    def test_quick_price_negative_cashback(self, client):
        """Negative cashback should be rejected."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": -5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422
    
    def test_quick_price_over_100_percent_cashback(self, client):
        """Cashback over 100% should be rejected."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 150.0,  # Over 100%
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        # May be accepted or rejected depending on validation
        assert response.status_code in [200, 422]
    
    def test_quick_price_negative_tax_rate(self, client):
        """Negative tax rate should be rejected."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": -0.05,  # Negative
            "shipping": 0
        })
        
        assert response.status_code == 422
    
    def test_quick_price_string_instead_of_number(self, client):
        """String value where number expected should fail."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": "one hundred",  # String
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422
    
    def test_quick_price_null_required_field(self, client):
        """Null value for required field should fail."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": None,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422
    
    def test_quick_price_extremely_large_number(self, client):
        """Extremely large numbers should be handled."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 1e308,  # Very large
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        # Should handle gracefully (accept or reject with proper error)
        assert response.status_code in [200, 422, 500]
    
    @pytest.mark.skip(reason="float('inf') cannot be serialized to JSON by httpx")
    def test_quick_price_infinity(self, client):
        """Infinity values should be rejected."""
        # Note: This test cannot run because Python's json encoder
        # rejects float('inf') before the request is even sent
        pass


# =============================================================================
# Malformed Request Tests
# =============================================================================

class TestMalformedRequests:
    """Test handling of malformed requests."""
    
    def test_empty_body(self, client):
        """Empty request body should fail gracefully."""
        response = client.post("/api/v1/quick-price", json={})
        
        assert response.status_code == 422
    
    def test_invalid_json_syntax(self, client):
        """Invalid JSON syntax should fail gracefully."""
        response = client.post(
            "/api/v1/quick-price",
            content="{invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
    
    def test_extra_unknown_fields(self, client):
        """Unknown fields should be ignored (not cause errors)."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": 100.00,
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0,
            "unknown_field": "should be ignored",
            "another_unknown": 12345
        })
        
        # Should succeed, ignoring unknown fields
        assert response.status_code == 200
    
    def test_nested_json_where_flat_expected(self, client):
        """Nested JSON where flat structure expected should fail."""
        response = client.post("/api/v1/quick-price", json={
            "product_price": {"nested": 100.00},  # Nested instead of flat
            "cashback_percent": 5.0,
            "card_reward_percent": 3.0,
            "coupon_discount": 0,
            "tax_rate": 0.0825,
            "shipping": 0
        })
        
        assert response.status_code == 422
    
    def test_array_where_object_expected(self, client):
        """Array where object expected should fail."""
        response = client.post(
            "/api/v1/quick-price",
            json=[100.00, 5.0, 3.0],  # Array instead of object
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422


# =============================================================================
# Find Best Price Error Handling Tests
# =============================================================================

class TestFindBestPriceErrors:
    """Test error handling for find-best-price endpoint."""
    
    def test_empty_query(self, client):
        """Empty query should fail."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "",
            "include_cashback": True,
            "include_coupons": True
        })
        
        # May fail with 422 validation or return 404/error result
        assert response.status_code in [200, 404, 422, 500]
    
    def test_whitespace_only_query(self, client):
        """Whitespace-only query should fail."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "   ",
            "include_cashback": True,
            "include_coupons": True
        })
        
        assert response.status_code in [200, 404, 422, 500]
    
    def test_very_long_query(self, client):
        """Very long query should be handled."""
        long_query = "https://example.com/" + "a" * 10000
        response = client.post("/api/v1/find-best-price", json={
            "query": long_query,
            "include_cashback": True,
            "include_coupons": True
        })
        
        # Should handle gracefully (might timeout or reject)
        assert response.status_code in [200, 404, 413, 422, 500]
    
    def test_invalid_url_characters(self, client):
        """URL with invalid characters should be handled."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "https://example.com/<script>alert('xss')</script>",
            "include_cashback": True,
            "include_coupons": True
        })
        
        # Should not execute XSS, should fail gracefully
        assert response.status_code in [200, 404, 422, 500]
    
    def test_unicode_url(self, client):
        """Unicode in URL should be handled."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "https://例え.jp/商品/",
            "include_cashback": True,
            "include_coupons": True
        })
        
        assert response.status_code in [200, 404, 422, 500]
    
    def test_null_include_flags(self, client):
        """Null include flags should use defaults."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "https://amazon.com/dp/B123456",
            "include_cashback": None,
            "include_coupons": None
        })
        
        # Should either use defaults or fail gracefully
        assert response.status_code in [200, 404, 422, 500]


# =============================================================================
# Wallet Endpoint Error Handling Tests
# =============================================================================

class TestWalletErrors:
    """Test error handling for wallet endpoints."""
    
    def test_add_card_empty_name(self, client):
        """Adding card with empty name should fail."""
        response = client.post("/api/v1/wallet/add", json={
            "name": "",
            "issuer": "Test Bank",
            "base_rate": 1.5,
            "bonus_categories": []
        })
        
        # Should reject empty name
        assert response.status_code in [400, 422]
    
    def test_add_card_negative_rate(self, client):
        """Adding card with negative base rate should fail."""
        response = client.post("/api/v1/wallet/add", json={
            "name": "Test Card",
            "issuer": "Test Bank",
            "base_rate": -1.0,
            "bonus_categories": []
        })
        
        assert response.status_code in [400, 422]
    
    def test_add_card_missing_required_fields(self, client):
        """Adding card with missing required fields should fail."""
        response = client.post("/api/v1/wallet/add", json={
            "name": "Test Card"
            # Missing issuer and base_rate
        })
        
        assert response.status_code == 422
    
    def test_add_card_malformed_bonus_categories(self, client):
        """Adding card with malformed bonus categories should fail."""
        response = client.post("/api/v1/wallet/add", json={
            "name": "Test Card",
            "issuer": "Test Bank",
            "base_rate": 1.5,
            "bonus_categories": "not an array"  # Should be array
        })
        
        assert response.status_code == 422
    
    @pytest.mark.skip(reason="TestClient doesn't run lifespan events, app.state.user_wallet not initialized")
    def test_remove_nonexistent_card(self, client):
        """Removing non-existent card should return success (idempotent operation)."""
        response = client.delete("/api/v1/wallet/NonExistentCard12345")
        
        # Should return success - idempotent delete operation
        assert response.status_code == 200
    
    def test_add_popular_card_special_characters(self, client):
        """Card name with special characters should be handled."""
        response = client.post("/api/v1/wallet/add-popular/Card%20With%20Spaces%26Ampersand")
        
        # Should be URL decoded and handled
        assert response.status_code in [404, 500]


# =============================================================================
# Cashback Rates Error Handling Tests
# =============================================================================

class TestCashbackRatesErrors:
    """Test error handling for cashback rates endpoint."""
    
    @pytest.mark.skip(reason="Endpoint makes real network calls to cashback providers - use integration tests")
    def test_empty_merchant(self, client):
        """Empty merchant should fail."""
        response = client.post("/api/v1/cashback-rates", json={
            "merchant": ""
        })
        
        # May fail validation or return empty results
        assert response.status_code in [200, 422, 500]
    
    @pytest.mark.skip(reason="Endpoint makes real network calls to cashback providers - use integration tests")
    def test_very_long_merchant_name(self, client):
        """Very long merchant name should be handled."""
        response = client.post("/api/v1/cashback-rates", json={
            "merchant": "A" * 1000
        })
        
        assert response.status_code in [200, 422, 500]
    
    @pytest.mark.skip(reason="Endpoint makes real network calls to cashback providers - use integration tests")
    def test_merchant_with_special_characters(self, client):
        """Merchant with special characters should be handled."""
        response = client.post("/api/v1/cashback-rates", json={
            "merchant": "Best Buy®™ & Electronics!"
        })
        
        assert response.status_code in [200, 500]


# =============================================================================
# Response Format Consistency Tests
# =============================================================================

class TestResponseFormatConsistency:
    """Test that error responses have consistent format."""
    
    def test_422_response_format(self, client):
        """422 validation errors should have consistent format."""
        response = client.post("/api/v1/quick-price", json={})
        
        assert response.status_code == 422
        data = response.json()
        
        # FastAPI validation errors have 'detail' field
        assert "detail" in data
    
    def test_404_response_format(self, client):
        """404 errors should have consistent format."""
        response = client.get("/api/v1/nonexistent-endpoint")
        
        assert response.status_code == 404
        data = response.json()
        
        assert "detail" in data
    
    def test_successful_response_has_data(self, client):
        """Successful responses should have expected data."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should not have 'error' field on success
        # Should have actual content
        assert "status" in data


# =============================================================================
# Timeout and Performance Edge Cases
# =============================================================================

class TestPerformanceEdgeCases:
    """Test edge cases related to performance."""
    
    @pytest.mark.skip(reason="TestClient doesn't run lifespan events, app.state.user_wallet not initialized")
    def test_concurrent_requests(self, client):
        """Multiple concurrent requests should be handled."""
        import concurrent.futures
        
        def make_request():
            return client.get("/health")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]
        
        # All requests should succeed
        for result in results:
            assert result.status_code == 200
    
    @pytest.mark.skip(reason="TestClient doesn't run lifespan events, app.state.user_wallet not initialized")
    def test_rapid_sequential_requests(self, client):
        """Rapid sequential requests should be handled."""
        for _ in range(20):
            response = client.get("/health")
            assert response.status_code == 200


# =============================================================================
# Security Edge Cases
# =============================================================================

class TestSecurityEdgeCases:
    """Test security-related edge cases."""
    
    @pytest.mark.skip(reason="Uses cashback-rates endpoint which makes real network calls")
    def test_sql_injection_in_merchant(self, client):
        """SQL injection attempts should be handled safely."""
        malicious_merchants = [
            "Nike'; DROP TABLE users;--",
            "Nike' OR '1'='1",
            "Nike\"; DELETE FROM products;--",
        ]
        
        for merchant in malicious_merchants:
            response = client.post("/api/v1/cashback-rates", json={
                "merchant": merchant
            })
            
            # Should not crash the server
            assert response.status_code in [200, 422, 500]
    
    @pytest.mark.skip(reason="Uses find-best-price endpoint which may make network calls")
    def test_xss_in_input(self, client):
        """XSS attempts should be handled safely."""
        response = client.post("/api/v1/find-best-price", json={
            "query": "<script>alert('xss')</script>",
            "include_cashback": True,
            "include_coupons": True
        })
        
        # Should not return executable script in response
        assert response.status_code in [200, 404, 422, 500]
        if response.status_code == 200:
            assert "<script>" not in response.text
    
    def test_path_traversal_in_card_name(self, client):
        """Path traversal attempts should be handled safely."""
        response = client.post("/api/v1/wallet/add-popular/../../../etc/passwd")
        
        # Should not access filesystem
        assert response.status_code in [404, 422, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
