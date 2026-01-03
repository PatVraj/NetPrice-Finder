"""
Credit Card Rewards Schema for SSIP
Defines card reward structures and calculates optimal payment strategies.
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import date, datetime
from enum import Enum
from pathlib import Path


class RewardType(Enum):
    """Type of reward earned."""
    CASHBACK = "cashback"
    POINTS = "points"
    MILES = "miles"


class BonusCategory(Enum):
    """Standard bonus spending categories."""
    GROCERIES = "groceries"
    DINING = "dining"
    GAS = "gas"
    TRAVEL = "travel"
    ENTERTAINMENT = "entertainment"
    STREAMING = "streaming"
    ONLINE_SHOPPING = "online_shopping"
    DRUGSTORES = "drugstores"
    HOME_IMPROVEMENT = "home_improvement"
    UTILITIES = "utilities"
    TRANSIT = "transit"
    ROTATING = "rotating"  # Quarterly rotating categories
    ALL = "all"  # Everything else


@dataclass
class RewardRate:
    """A reward rate for a specific category."""
    category: BonusCategory
    rate: float  # e.g., 3.0 for 3% or 3x points
    reward_type: RewardType
    cap_amount: Optional[float] = None  # Quarterly/annual cap
    cap_period: Optional[str] = None  # "quarterly", "annual", "monthly"
    activation_required: bool = False  # Some cards require activation
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["category"] = self.category.value
        result["reward_type"] = self.reward_type.value
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "RewardRate":
        data["category"] = BonusCategory(data["category"])
        data["reward_type"] = RewardType(data["reward_type"])
        return cls(**data)


@dataclass
class CreditCard:
    """A credit card with its reward structure."""
    name: str
    issuer: str
    reward_type: RewardType
    base_rate: float  # Rate for non-bonus categories
    annual_fee: float = 0.0
    
    # Bonus categories
    bonus_rates: list[RewardRate] = field(default_factory=list)
    
    # Point/mile valuation (cents per point)
    point_value: float = 1.0  # 1.0 = 1 cent per point
    
    # Sign-up bonus
    signup_bonus: Optional[float] = None
    signup_spend_requirement: Optional[float] = None
    signup_months: Optional[int] = None
    
    # Card benefits
    benefits: list[str] = field(default_factory=list)
    
    # Metadata
    card_id: Optional[str] = None
    last_updated: Optional[str] = None
    
    def __post_init__(self):
        if self.card_id is None:
            self.card_id = f"{self.issuer.lower().replace(' ', '_')}_{self.name.lower().replace(' ', '_')}"
    
    def get_rate_for_category(self, category: str | BonusCategory) -> tuple[float, RewardType]:
        """
        Get the best reward rate for a category.
        
        Returns:
            Tuple of (rate, reward_type)
        """
        if isinstance(category, str):
            try:
                category = BonusCategory(category.lower())
            except ValueError:
                category = BonusCategory.ALL
        
        today = date.today().isoformat()
        
        for rate in self.bonus_rates:
            if rate.category == category:
                # Check date validity
                if rate.valid_from and rate.valid_from > today:
                    continue
                if rate.valid_until and rate.valid_until < today:
                    continue
                return (rate.rate, rate.reward_type)
        
        return (self.base_rate, self.reward_type)
    
    def calculate_rewards(
        self,
        amount: float,
        category: str | BonusCategory,
    ) -> dict:
        """
        Calculate rewards for a purchase.
        
        Returns:
            Dict with reward amount and value
        """
        rate, reward_type = self.get_rate_for_category(category)
        
        if reward_type == RewardType.CASHBACK:
            rewards = amount * (rate / 100)
            cash_value = rewards
        else:
            rewards = amount * rate  # Points/miles earned
            cash_value = rewards * (self.point_value / 100)
        
        return {
            "amount": amount,
            "category": category.value if isinstance(category, BonusCategory) else category,
            "rate": rate,
            "reward_type": reward_type.value,
            "rewards_earned": rewards,
            "cash_value": cash_value,
            "card": self.name,
        }
    
    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "issuer": self.issuer,
            "reward_type": self.reward_type.value,
            "base_rate": self.base_rate,
            "annual_fee": self.annual_fee,
            "bonus_rates": [r.to_dict() for r in self.bonus_rates],
            "point_value": self.point_value,
            "signup_bonus": self.signup_bonus,
            "signup_spend_requirement": self.signup_spend_requirement,
            "signup_months": self.signup_months,
            "benefits": self.benefits,
            "card_id": self.card_id,
            "last_updated": self.last_updated,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "CreditCard":
        data["reward_type"] = RewardType(data["reward_type"])
        data["bonus_rates"] = [RewardRate.from_dict(r) for r in data.get("bonus_rates", [])]
        return cls(**data)


@dataclass
class CardWallet:
    """A collection of credit cards for optimization."""
    cards: list[CreditCard] = field(default_factory=list)
    
    def add_card(self, card: CreditCard):
        """Add a card to the wallet."""
        # Remove existing card with same ID
        self.cards = [c for c in self.cards if c.card_id != card.card_id]
        self.cards.append(card)
    
    def remove_card(self, card_id: str):
        """Remove a card from the wallet."""
        self.cards = [c for c in self.cards if c.card_id != card_id]
    
    def get_card(self, card_id: str) -> Optional[CreditCard]:
        """Get a card by ID."""
        for card in self.cards:
            if card.card_id == card_id:
                return card
        return None
    
    def get_best_card(self, category: str | BonusCategory, amount: float = 100.0) -> tuple[CreditCard, dict]:
        """
        Find the best card to use for a purchase in a category.
        
        Returns:
            Tuple of (best_card, reward_info)
        """
        if not self.cards:
            raise ValueError("No cards in wallet")
        
        best_card = None
        best_value = -1
        best_info = None
        
        for card in self.cards:
            info = card.calculate_rewards(amount, category)
            if info["cash_value"] > best_value:
                best_value = info["cash_value"]
                best_card = card
                best_info = info
        
        return (best_card, best_info)
    
    def get_recommendations(self, transactions: list[dict]) -> list[dict]:
        """
        Get card recommendations for a list of transactions.
        
        Args:
            transactions: List of dicts with 'amount' and 'category' keys
            
        Returns:
            List of recommendations with card and expected rewards
        """
        recommendations = []
        
        for tx in transactions:
            amount = tx.get("amount", 0)
            category = tx.get("category", "all")
            description = tx.get("description", "")
            
            if amount <= 0:
                continue
            
            best_card, reward_info = self.get_best_card(category, amount)
            
            recommendations.append({
                "description": description,
                "amount": amount,
                "category": category,
                "recommended_card": best_card.name,
                "card_issuer": best_card.issuer,
                "expected_rate": reward_info["rate"],
                "reward_type": reward_info["reward_type"],
                "expected_rewards": reward_info["rewards_earned"],
                "expected_cash_value": reward_info["cash_value"],
            })
        
        return recommendations
    
    def analyze_spending(self, transactions: list[dict]) -> dict:
        """
        Analyze spending and calculate potential rewards if optimal cards were used.
        
        Args:
            transactions: List of dicts with 'amount', 'category', and optionally 'card_used'
            
        Returns:
            Analysis with current vs optimal rewards
        """
        total_spent = 0
        actual_rewards = 0
        optimal_rewards = 0
        missed_rewards = 0
        
        by_category = {}
        
        for tx in transactions:
            amount = tx.get("amount", 0)
            category = tx.get("category", "all")
            card_used = tx.get("card_used")
            
            if amount <= 0:
                continue
            
            total_spent += amount
            
            # Calculate optimal
            best_card, best_info = self.get_best_card(category, amount)
            optimal_value = best_info["cash_value"]
            optimal_rewards += optimal_value
            
            # Calculate actual if card was specified
            if card_used:
                used_card = self.get_card(card_used) or next(
                    (c for c in self.cards if c.name.lower() == card_used.lower()), None
                )
                if used_card:
                    actual_info = used_card.calculate_rewards(amount, category)
                    actual_value = actual_info["cash_value"]
                else:
                    actual_value = 0  # Unknown card
            else:
                actual_value = optimal_value  # Assume optimal if not specified
            
            actual_rewards += actual_value
            missed_rewards += (optimal_value - actual_value)
            
            # Track by category
            if category not in by_category:
                by_category[category] = {
                    "total": 0,
                    "actual_rewards": 0,
                    "optimal_rewards": 0,
                    "best_card": None,
                }
            by_category[category]["total"] += amount
            by_category[category]["actual_rewards"] += actual_value
            by_category[category]["optimal_rewards"] += optimal_value
            by_category[category]["best_card"] = best_card.name
        
        return {
            "total_spent": total_spent,
            "actual_rewards": round(actual_rewards, 2),
            "optimal_rewards": round(optimal_rewards, 2),
            "missed_rewards": round(missed_rewards, 2),
            "optimization_potential": round((missed_rewards / actual_rewards * 100) if actual_rewards > 0 else 0, 1),
            "by_category": by_category,
        }
    
    def to_dict(self) -> dict:
        return {
            "cards": [c.to_dict() for c in self.cards],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CardWallet":
        wallet = cls()
        for card_data in data.get("cards", []):
            wallet.add_card(CreditCard.from_dict(card_data))
        return wallet
    
    def save(self, path: str | Path):
        """Save wallet to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str | Path) -> "CardWallet":
        """Load wallet from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


# =============================================================================
# Pre-defined Popular Cards
# =============================================================================

def create_chase_sapphire_preferred() -> CreditCard:
    """Chase Sapphire Preferred card."""
    return CreditCard(
        name="Sapphire Preferred",
        issuer="Chase",
        reward_type=RewardType.POINTS,
        base_rate=1.0,
        annual_fee=95.0,
        point_value=1.25,  # 1.25 cents when redeemed via portal
        bonus_rates=[
            RewardRate(BonusCategory.TRAVEL, 5.0, RewardType.POINTS),
            RewardRate(BonusCategory.DINING, 3.0, RewardType.POINTS),
            RewardRate(BonusCategory.STREAMING, 3.0, RewardType.POINTS),
            RewardRate(BonusCategory.ONLINE_SHOPPING, 3.0, RewardType.POINTS),
        ],
        signup_bonus=60000,
        signup_spend_requirement=4000,
        signup_months=3,
        benefits=[
            "Primary car rental insurance",
            "Trip cancellation insurance",
            "No foreign transaction fees",
            "$50 annual hotel credit",
        ],
    )


def create_amex_gold() -> CreditCard:
    """American Express Gold card."""
    return CreditCard(
        name="Gold Card",
        issuer="American Express",
        reward_type=RewardType.POINTS,
        base_rate=1.0,
        annual_fee=250.0,
        point_value=1.0,
        bonus_rates=[
            RewardRate(BonusCategory.DINING, 4.0, RewardType.POINTS),
            RewardRate(BonusCategory.GROCERIES, 4.0, RewardType.POINTS, cap_amount=25000, cap_period="annual"),
        ],
        signup_bonus=60000,
        signup_spend_requirement=6000,
        signup_months=6,
        benefits=[
            "$120 dining credit",
            "$120 Uber Cash",
            "No foreign transaction fees",
        ],
    )


def create_citi_double_cash() -> CreditCard:
    """Citi Double Cash card - 2% on everything."""
    return CreditCard(
        name="Double Cash",
        issuer="Citi",
        reward_type=RewardType.CASHBACK,
        base_rate=2.0,  # 1% on purchase + 1% on payment
        annual_fee=0.0,
        bonus_rates=[],  # Flat rate card
        benefits=[
            "No annual fee",
            "Balance transfer offers",
        ],
    )


def create_chase_freedom_flex() -> CreditCard:
    """Chase Freedom Flex with 5% rotating categories."""
    return CreditCard(
        name="Freedom Flex",
        issuer="Chase",
        reward_type=RewardType.POINTS,
        base_rate=1.0,
        annual_fee=0.0,
        point_value=1.0,
        bonus_rates=[
            RewardRate(
                BonusCategory.ROTATING, 5.0, RewardType.POINTS,
                cap_amount=1500, cap_period="quarterly",
                activation_required=True,
            ),
            RewardRate(BonusCategory.TRAVEL, 5.0, RewardType.POINTS),
            RewardRate(BonusCategory.DINING, 3.0, RewardType.POINTS),
            RewardRate(BonusCategory.DRUGSTORES, 3.0, RewardType.POINTS),
        ],
        benefits=[
            "No annual fee",
            "5% rotating categories (activate quarterly)",
            "Cell phone protection",
        ],
    )


def create_discover_it() -> CreditCard:
    """Discover it with 5% rotating categories and first year match."""
    return CreditCard(
        name="it Cash Back",
        issuer="Discover",
        reward_type=RewardType.CASHBACK,
        base_rate=1.0,
        annual_fee=0.0,
        bonus_rates=[
            RewardRate(
                BonusCategory.ROTATING, 5.0, RewardType.CASHBACK,
                cap_amount=1500, cap_period="quarterly",
                activation_required=True,
            ),
        ],
        benefits=[
            "No annual fee",
            "Cashback Match first year",
            "No foreign transaction fees",
        ],
    )


def create_amazon_prime_visa() -> CreditCard:
    """Amazon Prime Visa."""
    return CreditCard(
        name="Prime Visa",
        issuer="Chase",
        reward_type=RewardType.CASHBACK,
        base_rate=1.0,
        annual_fee=0.0,
        bonus_rates=[
            RewardRate(BonusCategory.ONLINE_SHOPPING, 5.0, RewardType.CASHBACK),  # Amazon/Whole Foods
            RewardRate(BonusCategory.DINING, 2.0, RewardType.CASHBACK),
            RewardRate(BonusCategory.GAS, 2.0, RewardType.CASHBACK),
            RewardRate(BonusCategory.TRANSIT, 2.0, RewardType.CASHBACK),
        ],
        benefits=[
            "No annual fee (with Prime)",
            "5% back at Amazon and Whole Foods",
            "No foreign transaction fees",
        ],
    )


def create_default_wallet() -> CardWallet:
    """Create a wallet with popular cards for testing."""
    wallet = CardWallet()
    wallet.add_card(create_chase_sapphire_preferred())
    wallet.add_card(create_amex_gold())
    wallet.add_card(create_citi_double_cash())
    wallet.add_card(create_chase_freedom_flex())
    wallet.add_card(create_discover_it())
    wallet.add_card(create_amazon_prime_visa())
    return wallet


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    # Create sample wallet
    wallet = create_default_wallet()
    
    print("=== Card Wallet ===")
    for card in wallet.cards:
        print(f"\n{card.issuer} {card.name}")
        print(f"  Base rate: {card.base_rate}{'%' if card.reward_type == RewardType.CASHBACK else 'x'}")
        print(f"  Annual fee: ${card.annual_fee}")
        for rate in card.bonus_rates[:3]:  # Show first 3 bonus categories
            print(f"  {rate.category.value}: {rate.rate}{'%' if rate.reward_type == RewardType.CASHBACK else 'x'}")
    
    print("\n=== Best Card by Category ===")
    categories = ["groceries", "dining", "gas", "travel", "online_shopping"]
    for cat in categories:
        best_card, info = wallet.get_best_card(cat, 100)
        print(f"{cat}: {best_card.name} ({info['rate']}{'%' if info['reward_type'] == 'cashback' else 'x'} = ${info['cash_value']:.2f} on $100)")
    
    print("\n=== Sample Spending Analysis ===")
    sample_transactions = [
        {"amount": 500, "category": "groceries", "description": "Whole Foods"},
        {"amount": 200, "category": "dining", "description": "Restaurants"},
        {"amount": 150, "category": "gas", "description": "Gas stations"},
        {"amount": 100, "category": "travel", "description": "Uber"},
        {"amount": 300, "category": "online_shopping", "description": "Amazon"},
    ]
    
    analysis = wallet.analyze_spending(sample_transactions)
    print(f"Total Spent: ${analysis['total_spent']:.2f}")
    print(f"Optimal Rewards: ${analysis['optimal_rewards']:.2f}")
    
    print("\n=== Recommendations ===")
    recs = wallet.get_recommendations(sample_transactions)
    for rec in recs:
        print(f"${rec['amount']:.0f} {rec['category']}: Use {rec['recommended_card']} ({rec['expected_rate']}x = ${rec['expected_cash_value']:.2f})")
