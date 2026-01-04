#!/usr/bin/env python3
"""Quick test script for CashbackMonitor"""
import asyncio
import logging

# Suppress debug output
for name in logging.Logger.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

from cashback.monitor import CashbackMonitor

async def test():
    m = CashbackMonitor()
    result = await m.find_best_cashback('Nike')
    return result

result = asyncio.run(test())
print("\n" + "="*50)
print(" CASHBACK RESULTS FOR NIKE")
print("="*50)
if result.best_offer:
    print(f" BEST: {result.best_offer.platform.value.upper()} - {result.best_offer.cashback_percent}% Cash Back")
else:
    print(" No offers found")
print("\n ALL OFFERS:")
for o in result.all_offers:
    print(f"   - {o.platform.value}: {o.cashback_percent}%")
if not result.all_offers:
    print("   (none)")
print("="*50)
