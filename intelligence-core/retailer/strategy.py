"""
Strategy Engine for Retailer Intelligence.
Calculates optimal savings strategies considering stacking rules.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime

from .models import (
    RetailerDeals,
    SavingsStrategy,
    StrategyOption,
    StoredCashbackOffer,
    StoredPromoCode,
    PaymentBonus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Stacking Rules
# =============================================================================

# Define which savings sources can be combined
# Key: tuple of (source1, source2), Value: "stack" or "conflict"
STACKING_RULES = {
    # Cashback platforms don't stack with each other
    ("rakuten", "topcashback"): "conflict",
    ("rakuten", "honey"): "conflict",
    ("rakuten", "befrugal"): "conflict",
    ("rakuten", "swagbucks"): "conflict",
    ("topcashback", "honey"): "conflict",
    ("topcashback", "befrugal"): "conflict",
    ("topcashback", "swagbucks"): "conflict",
    ("honey", "befrugal"): "conflict",
    ("honey", "swagbucks"): "conflict",
    ("befrugal", "swagbucks"): "conflict",
    
    # Cashback stacks with credit cards
    ("rakuten", "credit_card"): "stack",
    ("topcashback", "credit_card"): "stack",
    ("honey", "credit_card"): "stack",
    ("befrugal", "credit_card"): "stack",
    ("swagbucks", "credit_card"): "stack",
    
    # Cashback stacks with PayPal rewards
    ("rakuten", "paypal"): "stack",
    ("topcashback", "paypal"): "stack",
    ("honey", "paypal"): "stack",
    ("befrugal", "paypal"): "stack",
    ("swagbucks", "paypal"): "stack",
    
    # Promo codes stack with everything
    ("promo_code", "rakuten"): "stack",
    ("promo_code", "topcashback"): "stack",
    ("promo_code", "honey"): "stack",
    ("promo_code", "befrugal"): "stack",
    ("promo_code", "swagbucks"): "stack",
    ("promo_code", "credit_card"): "stack",
    ("promo_code", "paypal"): "stack",
    
    # PayPal stacks with credit cards (PayPal Key, etc.)
    ("paypal", "credit_card"): "stack",
    
    # Venmo similar to PayPal
    ("venmo", "credit_card"): "stack",
    ("venmo", "rakuten"): "stack",
    ("venmo", "promo_code"): "stack",
}


def can_stack(source1: str, source2: str) -> bool:
    """
    Check if two savings sources can be stacked.
    
    Args:
        source1: First source (e.g., "rakuten", "credit_card")
        source2: Second source
        
    Returns:
        True if they can be combined
    """
    if source1 == source2:
        return False
    
    # Normalize sources
    s1 = source1.lower()
    s2 = source2.lower()
    
    # Check both orderings
    key1 = (s1, s2)
    key2 = (s2, s1)
    
    if key1 in STACKING_RULES:
        return STACKING_RULES[key1] == "stack"
    if key2 in STACKING_RULES:
        return STACKING_RULES[key2] == "stack"
    
    # Default: assume stackable if not explicitly conflicting
    return True


# =============================================================================
# Strategy Calculator
# =============================================================================

class StrategyCalculator:
    """
    Calculate optimal savings strategies for purchases.
    
    Considers:
    - Multiple cashback platforms
    - Promo codes with minimum purchase requirements
    - Credit card category bonuses
    - Payment method bonuses (PayPal, etc.)
    - Stacking rules
    """
    
    def __init__(self, card_wallet: Optional[Any] = None):
        """
        Initialize strategy calculator.
        
        Args:
            card_wallet: Optional CardWallet for credit card optimization
        """
        self.card_wallet = card_wallet
    
    def calculate_strategy(
        self,
        deals: RetailerDeals,
        purchase_amount: float,
        product_category: Optional[str] = None,
    ) -> SavingsStrategy:
        """
        Calculate optimal savings strategy for a purchase.
        
        Args:
            deals: All available deals for the retailer
            purchase_amount: Purchase amount in dollars
            product_category: Product category for CC rewards
            
        Returns:
            SavingsStrategy with ranked options
        """
        all_strategies = []
        
        # Generate strategies for each cashback platform
        for cashback in deals.cashback_offers:
            strategy = self._build_strategy(
                purchase_amount=purchase_amount,
                cashback=cashback,
                promos=deals.promo_codes,
                payment_bonuses=deals.payment_bonuses,
                product_category=product_category,
            )
            all_strategies.append(strategy)
        
        # Also generate a "no cashback" strategy (just promo + CC)
        if deals.promo_codes or self.card_wallet:
            no_cashback_strategy = self._build_strategy(
                purchase_amount=purchase_amount,
                cashback=None,
                promos=deals.promo_codes,
                payment_bonuses=deals.payment_bonuses,
                product_category=product_category,
            )
            if no_cashback_strategy.total_savings_amount > 0:
                all_strategies.append(no_cashback_strategy)
        
        # Sort by total savings
        all_strategies.sort(
            key=lambda s: s.total_savings_amount,
            reverse=True
        )
        
        # Build final strategy result
        best = all_strategies[0] if all_strategies else None
        
        strategy = SavingsStrategy(
            retailer=deals.retailer,
            purchase_amount=purchase_amount,
            recommended_strategy=best,
            all_strategies=all_strategies,
        )
        
        # Calculate summary totals
        if best:
            strategy.max_cashback_percent = best.cashback_percent
            strategy.max_promo_value = best.promo_discount
            strategy.max_cc_rewards_percent = best.cc_reward_percent
            strategy.estimated_total_savings = best.total_savings_amount
            strategy.estimated_net_price = best.net_price
            strategy.steps = self._generate_steps(best)
        else:
            strategy.estimated_net_price = purchase_amount
        
        return strategy
    
    def _build_strategy(
        self,
        purchase_amount: float,
        cashback: Optional[StoredCashbackOffer],
        promos: list[StoredPromoCode],
        payment_bonuses: list[PaymentBonus],
        product_category: Optional[str] = None,
    ) -> StrategyOption:
        """Build a single strategy option."""
        
        # Initialize totals
        cashback_percent = 0.0
        cashback_amount = 0.0
        promo_discount = 0.0
        cc_reward_percent = 0.0
        cc_reward_amount = 0.0
        payment_bonus_percent = 0.0
        payment_bonus_amount = 0.0
        
        name_parts = []
        conflicts = []
        
        # Add cashback if available
        cashback_platform = None
        if cashback:
            cashback_platform = cashback.platform
            cashback_percent = cashback.effective_rate
            cashback_amount = purchase_amount * (cashback_percent / 100)
            name_parts.append(cashback.platform.title())
        
        # Find best stackable promo code
        best_promo = None
        best_promo_code = None
        best_promo_desc = None
        
        for promo in promos:
            # Check if promo stacks with cashback
            if cashback and not can_stack("promo_code", cashback.platform):
                conflicts.append(f"Promo conflicts with {cashback.platform}")
                continue
            
            # Calculate actual discount
            discount = promo.calculate_discount(purchase_amount)
            if discount > promo_discount:
                promo_discount = discount
                best_promo = promo
                best_promo_code = promo.code
                best_promo_desc = promo.description
        
        if best_promo:
            name_parts.append(f"Code: {best_promo.code}")
        
        # Add credit card rewards
        cc_name = None
        if self.card_wallet and product_category:
            try:
                best_card, card_info = self.card_wallet.get_best_card(
                    product_category,
                    purchase_amount - promo_discount,  # After promo
                )
                
                # Check stacking with cashback
                if cashback and not can_stack("credit_card", cashback.platform):
                    conflicts.append(f"CC conflicts with {cashback.platform}")
                else:
                    cc_name = best_card.name
                    cc_reward_percent = card_info["rate"]
                    cc_reward_amount = card_info["cash_value"]
                    name_parts.append(best_card.name)
            except Exception:
                pass
        
        # Add payment bonus
        payment_method = None
        best_payment_bonus = None
        
        for bonus in payment_bonuses:
            # Check stacking
            stackable = True
            if cashback and not can_stack(str(bonus.method.value), cashback.platform):
                stackable = False
            
            if stackable and bonus.bonus_value > payment_bonus_percent:
                payment_bonus_percent = bonus.bonus_value
                payment_bonus_amount = purchase_amount * (bonus.bonus_value / 100)
                payment_method = str(bonus.method.value)
                best_payment_bonus = bonus
        
        if best_payment_bonus:
            name_parts.append(f"via {payment_method.title()}")
        
        # Calculate totals
        total_savings_amount = (
            cashback_amount +
            promo_discount +
            cc_reward_amount +
            payment_bonus_amount
        )
        
        total_savings_percent = (total_savings_amount / purchase_amount) * 100 if purchase_amount > 0 else 0
        net_price = purchase_amount - promo_discount  # Only promo is subtracted from price
        
        # Build name
        name = " + ".join(name_parts) if name_parts else "No Savings"
        
        return StrategyOption(
            name=name,
            cashback_platform=cashback_platform,
            cashback_percent=cashback_percent,
            cashback_amount=cashback_amount,
            promo_code=best_promo_code,
            promo_description=best_promo_desc,
            promo_discount=promo_discount,
            credit_card=cc_name,
            cc_reward_percent=cc_reward_percent,
            cc_reward_amount=cc_reward_amount,
            payment_method=payment_method,
            payment_bonus_percent=payment_bonus_percent,
            payment_bonus_amount=payment_bonus_amount,
            total_savings_percent=total_savings_percent,
            total_savings_amount=total_savings_amount,
            net_price=net_price,
            is_stackable=len(conflicts) == 0,
            conflicts=conflicts,
        )
    
    def _generate_steps(self, strategy: StrategyOption) -> list[str]:
        """Generate human-readable steps for a strategy."""
        steps = []
        
        if strategy.promo_code:
            steps.append(f"Apply code '{strategy.promo_code}' for ${strategy.promo_discount:.2f} off")
        
        if strategy.cashback_platform:
            steps.append(
                f"Go through {strategy.cashback_platform.title()} for "
                f"{strategy.cashback_percent:.1f}% cashback (${strategy.cashback_amount:.2f})"
            )
        
        if strategy.payment_method:
            steps.append(
                f"Pay with {strategy.payment_method.title()} for "
                f"{strategy.payment_bonus_percent:.1f}% bonus (${strategy.payment_bonus_amount:.2f})"
            )
        
        if strategy.credit_card:
            steps.append(
                f"Use {strategy.credit_card} card for "
                f"{strategy.cc_reward_percent:.1f}% rewards (${strategy.cc_reward_amount:.2f})"
            )
        
        if steps:
            steps.append(
                f"Total savings: ${strategy.total_savings_amount:.2f} "
                f"({strategy.total_savings_percent:.1f}%)"
            )
        
        return steps


def calculate_best_strategy(
    deals: RetailerDeals,
    purchase_amount: float,
    card_wallet: Optional[Any] = None,
    product_category: Optional[str] = None,
) -> SavingsStrategy:
    """
    Convenience function to calculate best savings strategy.
    
    Args:
        deals: Retailer deals
        purchase_amount: Purchase amount
        card_wallet: Optional credit card wallet
        product_category: Product category for CC rewards
        
    Returns:
        Optimal savings strategy
    """
    calculator = StrategyCalculator(card_wallet=card_wallet)
    return calculator.calculate_strategy(
        deals=deals,
        purchase_amount=purchase_amount,
        product_category=product_category,
    )
