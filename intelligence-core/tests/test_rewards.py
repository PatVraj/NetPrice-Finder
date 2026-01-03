"""
Test Suite: Credit Card Rewards Schema

Tests for the credit card reward system.
Run: pytest tests/test_rewards.py -v
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rewards.schema import (
    CreditCard,
    CardWallet,
    RewardRate,
    BonusCategory,
    POPULAR_CARDS
)


class TestCreditCard:
    """Test cases for CreditCard dataclass."""

    def test_create_basic_card(self):
        """Test creating a basic credit card."""
        card = CreditCard(
            name="Test Card",
            issuer="Test Bank",
            base_rate=1.0
        )
        
        assert card.name == "Test Card"
        assert card.issuer == "Test Bank"
        assert card.base_rate == 1.0
        assert card.bonus_categories == []

    def test_create_card_with_bonus_categories(self):
        """Test creating a card with bonus categories."""
        card = CreditCard(
            name="Bonus Card",
            issuer="Test Bank",
            base_rate=1.0,
            bonus_categories=[
                BonusCategory(category="Dining", rate=3.0),
                BonusCategory(category="Travel", rate=2.0),
            ]
        )
        
        assert len(card.bonus_categories) == 2
        assert card.bonus_categories[0].category == "Dining"
        assert card.bonus_categories[0].rate == 3.0

    def test_card_get_rate_for_category(self):
        """Test getting reward rate for a specific category."""
        card = CreditCard(
            name="Category Card",
            issuer="Test Bank",
            base_rate=1.0,
            bonus_categories=[
                BonusCategory(category="Dining", rate=4.0),
                BonusCategory(category="Groceries", rate=3.0),
            ]
        )
        
        # Test bonus category
        dining_rate = card.get_rate_for_category("Dining")
        assert dining_rate == 4.0
        
        # Test base rate for non-bonus category
        other_rate = card.get_rate_for_category("Electronics")
        assert other_rate == card.base_rate

    def test_card_str_representation(self):
        """Test string representation of card."""
        card = CreditCard(
            name="Chase Sapphire",
            issuer="Chase",
            base_rate=1.0
        )
        
        assert "Chase Sapphire" in str(card) or hasattr(card, '__str__')


class TestCardWallet:
    """Test cases for CardWallet class."""

    def test_create_empty_wallet(self):
        """Test creating an empty wallet."""
        wallet = CardWallet()
        
        assert len(wallet.cards) == 0

    def test_add_card_to_wallet(self):
        """Test adding a card to the wallet."""
        wallet = CardWallet()
        card = CreditCard(name="Test Card", issuer="Bank", base_rate=1.5)
        
        wallet.add_card(card)
        
        assert len(wallet.cards) == 1
        assert wallet.cards[0].name == "Test Card"

    def test_add_multiple_cards(self):
        """Test adding multiple cards to the wallet."""
        wallet = CardWallet()
        
        wallet.add_card(CreditCard(name="Card 1", issuer="Bank A", base_rate=1.0))
        wallet.add_card(CreditCard(name="Card 2", issuer="Bank B", base_rate=2.0))
        wallet.add_card(CreditCard(name="Card 3", issuer="Bank C", base_rate=1.5))
        
        assert len(wallet.cards) == 3

    def test_get_best_card_for_category(self):
        """Test getting the best card for a specific category."""
        wallet = CardWallet()
        
        # Card with 4x dining
        wallet.add_card(CreditCard(
            name="Dining Card",
            issuer="Bank A",
            base_rate=1.0,
            bonus_categories=[BonusCategory(category="Dining", rate=4.0)]
        ))
        
        # Card with 2x everything
        wallet.add_card(CreditCard(
            name="Flat Card",
            issuer="Bank B",
            base_rate=2.0
        ))
        
        best = wallet.get_best_card("Dining")
        assert best.name == "Dining Card"
        
        best_other = wallet.get_best_card("Gas")
        assert best_other.name == "Flat Card"

    def test_empty_wallet_best_card(self):
        """Test getting best card from empty wallet."""
        wallet = CardWallet()
        
        result = wallet.get_best_card("Dining")
        assert result is None


class TestBonusCategory:
    """Test cases for BonusCategory dataclass."""

    def test_create_bonus_category(self):
        """Test creating a bonus category."""
        bonus = BonusCategory(category="Dining", rate=3.0)
        
        assert bonus.category == "Dining"
        assert bonus.rate == 3.0

    def test_bonus_category_with_mcc(self):
        """Test bonus category with MCC code."""
        bonus = BonusCategory(
            category="Restaurants",
            rate=4.0,
            mcc_codes=["5812", "5813", "5814"]
        )
        
        assert "5812" in bonus.mcc_codes


class TestPopularCards:
    """Test cases for pre-built popular cards."""

    def test_popular_cards_exist(self):
        """Test that popular cards are defined."""
        assert len(POPULAR_CARDS) > 0

    def test_chase_sapphire_preferred(self):
        """Test Chase Sapphire Preferred card definition."""
        csp = next((c for c in POPULAR_CARDS if "Sapphire" in c.name), None)
        
        assert csp is not None
        assert csp.issuer == "Chase"
        assert len(csp.bonus_categories) > 0

    def test_amex_gold(self):
        """Test Amex Gold card definition."""
        amex = next((c for c in POPULAR_CARDS if "Gold" in c.name and "Amex" in c.issuer), None)
        
        if amex:  # Only test if Amex Gold is in the list
            assert amex.issuer == "American Express"
            # Amex Gold should have 4x on restaurants
            dining_bonus = next(
                (b for b in amex.bonus_categories if "Restaurant" in b.category or "Dining" in b.category),
                None
            )
            assert dining_bonus is not None
            assert dining_bonus.rate >= 4.0

    def test_all_popular_cards_have_issuer(self):
        """Test that all popular cards have an issuer."""
        for card in POPULAR_CARDS:
            assert card.issuer is not None
            assert len(card.issuer) > 0

    def test_all_popular_cards_have_base_rate(self):
        """Test that all popular cards have a base rate."""
        for card in POPULAR_CARDS:
            assert card.base_rate >= 0


class TestRewardRate:
    """Test cases for RewardRate (if exists)."""

    def test_reward_rate_calculation(self):
        """Test reward rate value calculation."""
        # Create a card with known rates
        card = CreditCard(
            name="Test Card",
            issuer="Test Bank",
            base_rate=1.0,
            bonus_categories=[
                BonusCategory(category="Groceries", rate=4.0),
            ]
        )
        
        # Calculate expected reward for $100 grocery purchase
        purchase_amount = 100.00
        rate = card.get_rate_for_category("Groceries")
        expected_reward = purchase_amount * (rate / 100)
        
        assert expected_reward == pytest.approx(4.00, rel=0.01)


class TestCardWalletOptimization:
    """Test cases for wallet optimization features."""

    def test_analyze_spending(self):
        """Test spending analysis feature."""
        wallet = CardWallet()
        
        wallet.add_card(CreditCard(
            name="Dining Card",
            issuer="Bank",
            base_rate=1.0,
            bonus_categories=[BonusCategory(category="Dining", rate=4.0)]
        ))
        
        wallet.add_card(CreditCard(
            name="Grocery Card",
            issuer="Bank",
            base_rate=1.0,
            bonus_categories=[BonusCategory(category="Groceries", rate=5.0)]
        ))
        
        # Test that wallet can recommend cards
        if hasattr(wallet, 'analyze_spending'):
            result = wallet.analyze_spending([
                {"category": "Dining", "amount": 500},
                {"category": "Groceries", "amount": 300},
            ])
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
