"""
Test Suite: Net Price Optimizer

Tests for the core net price calculation logic.
Run: pytest tests/test_net_price.py -v
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from optimizer.net_price import calculate_net_price


class TestCalculateNetPrice:
    """Test cases for calculate_net_price function."""

    def test_basic_calculation(self):
        """Test basic net price calculation with all parameters."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=5.0,
            card_reward_percent=3.0,
            coupon_discount=10.00,
            tax_rate=0.0825,
            shipping=0.00
        )
        
        assert result["product_price"] == 100.00
        assert result["coupon_discount"] == 10.00
        assert result["tax"] == pytest.approx(8.25, rel=0.01)
        assert result["shipping"] == 0.00
        assert result["gross_total"] == pytest.approx(98.25, rel=0.01)
        assert result["cashback"] == pytest.approx(4.91, rel=0.01)
        assert result["card_rewards"] == pytest.approx(2.95, rel=0.01)
        assert result["net_price"] == pytest.approx(90.39, rel=0.01)
        assert result["total_savings"] > 0
        assert result["savings_percent"] > 0

    def test_no_discounts(self):
        """Test with no discounts applied."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0.0825,
            shipping=0
        )
        
        assert result["product_price"] == 100.00
        assert result["cashback"] == 0.00
        assert result["card_rewards"] == 0.00
        assert result["gross_total"] == result["net_price"]
        assert result["savings_percent"] == pytest.approx(0, rel=0.01)

    def test_cashback_only(self):
        """Test with only cashback applied."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=10.0,
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0,
            shipping=0
        )
        
        assert result["cashback"] == pytest.approx(10.00, rel=0.01)
        assert result["card_rewards"] == 0.00
        assert result["net_price"] == pytest.approx(90.00, rel=0.01)
        assert result["savings_percent"] == pytest.approx(10.0, rel=0.1)

    def test_card_rewards_only(self):
        """Test with only card rewards applied."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=5.0,
            coupon_discount=0,
            tax_rate=0,
            shipping=0
        )
        
        assert result["cashback"] == 0.00
        assert result["card_rewards"] == pytest.approx(5.00, rel=0.01)
        assert result["net_price"] == pytest.approx(95.00, rel=0.01)

    def test_coupon_only(self):
        """Test with only coupon discount applied."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=20.00,
            tax_rate=0,
            shipping=0
        )
        
        assert result["coupon_discount"] == 20.00
        assert result["gross_total"] == 80.00
        assert result["net_price"] == 80.00

    def test_with_shipping(self):
        """Test with shipping cost included."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0,
            shipping=9.99
        )
        
        assert result["shipping"] == 9.99
        assert result["gross_total"] == 109.99
        assert result["net_price"] == 109.99

    def test_with_tax(self):
        """Test with tax applied."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0.10,  # 10% tax
            shipping=0
        )
        
        assert result["tax"] == pytest.approx(10.00, rel=0.01)
        assert result["gross_total"] == pytest.approx(110.00, rel=0.01)

    def test_all_savings_stacked(self):
        """Test with all savings types stacked together."""
        result = calculate_net_price(
            product_price=150.00,
            cashback_percent=8.0,      # 8% Rakuten
            card_reward_percent=4.0,   # 4x Amex Gold
            coupon_discount=25.00,     # $25 off coupon
            tax_rate=0.0825,           # 8.25% tax
            shipping=0
        )
        
        # Verify the calculation chain
        assert result["product_price"] == 150.00
        assert result["coupon_discount"] == 25.00
        
        # After coupon: 150 - 25 = 125
        # After tax: 125 + (150 * 0.0825) = 125 + 12.375 = 137.375
        assert result["gross_total"] == pytest.approx(137.375, rel=0.01)
        
        # Cashback and card rewards on gross
        assert result["cashback"] > 0
        assert result["card_rewards"] > 0
        
        # Net price should be significantly lower
        assert result["net_price"] < result["gross_total"]
        assert result["savings_percent"] > 15  # Should save more than 15%

    def test_zero_price(self):
        """Test with zero product price (edge case)."""
        result = calculate_net_price(
            product_price=0,
            cashback_percent=5,
            card_reward_percent=3,
            coupon_discount=0,
            tax_rate=0.0825,
            shipping=0
        )
        
        assert result["net_price"] == 0
        assert result["savings_percent"] == 0

    def test_large_coupon(self):
        """Test when coupon is larger than product price."""
        result = calculate_net_price(
            product_price=50.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=100.00,  # Coupon > product price
            tax_rate=0,
            shipping=0
        )
        
        # Coupon shouldn't make price negative (implementation-dependent)
        # This tests the edge case handling
        assert result["coupon_discount"] == 100.00
        # The gross_total could be negative depending on implementation

    def test_high_cashback_rate(self):
        """Test with high cashback rate."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=25.0,  # 25% cashback (special promo)
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0,
            shipping=0
        )
        
        assert result["cashback"] == pytest.approx(25.00, rel=0.01)
        assert result["net_price"] == pytest.approx(75.00, rel=0.01)

    def test_realistic_nike_purchase(self):
        """Test a realistic Nike shoe purchase scenario."""
        result = calculate_net_price(
            product_price=120.00,    # Nike shoes
            cashback_percent=6.0,    # TopCashback 6%
            card_reward_percent=3.0, # Chase Sapphire 3x
            coupon_discount=18.00,   # 15% off with NIKE15
            tax_rate=0.0825,         # Texas tax
            shipping=0               # Free shipping
        )
        
        # Verify it's a good deal
        assert result["total_savings"] > 15  # Should save at least $15
        assert result["savings_percent"] > 12  # At least 12% savings

    def test_amazon_prime_purchase(self):
        """Test a realistic Amazon Prime purchase scenario."""
        result = calculate_net_price(
            product_price=79.99,     # Amazon product
            cashback_percent=1.0,    # Rakuten 1%
            card_reward_percent=5.0, # Amazon Prime Visa 5%
            coupon_discount=0,       # No coupon
            tax_rate=0.0825,         # Tax
            shipping=0               # Prime free shipping
        )
        
        # Amazon Prime Visa should be the major saver here
        assert result["card_rewards"] > result["cashback"]


class TestCalculateNetPriceDefaults:
    """Test default parameter handling."""

    def test_default_shipping(self):
        """Test that shipping defaults to 0."""
        result = calculate_net_price(
            product_price=100.00,
            cashback_percent=0,
            card_reward_percent=0,
            coupon_discount=0,
            tax_rate=0
        )
        
        assert result["shipping"] == 0

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        result = calculate_net_price(100, 5, 3, 10, 0.0825, 0)
        
        assert isinstance(result, dict)
        assert "net_price" in result
        assert "total_savings" in result
        assert "savings_percent" in result


class TestCalculateNetPriceEdgeCases:
    """Edge case tests for robustness."""

    def test_decimal_precision(self):
        """Test decimal precision handling."""
        result = calculate_net_price(
            product_price=99.99,
            cashback_percent=5.5,
            card_reward_percent=2.25,
            coupon_discount=10.00,
            tax_rate=0.0825,
            shipping=4.99
        )
        
        # Ensure all values are reasonable numbers
        assert isinstance(result["net_price"], (int, float))
        assert result["net_price"] > 0

    def test_small_values(self):
        """Test with very small values."""
        result = calculate_net_price(
            product_price=0.99,
            cashback_percent=1,
            card_reward_percent=1,
            coupon_discount=0,
            tax_rate=0.0825,
            shipping=0
        )
        
        assert result["net_price"] < result["product_price"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
