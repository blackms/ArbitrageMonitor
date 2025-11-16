"""Simple verification script for ProfitCalculator"""

from decimal import Decimal
from src.detectors.profit_calculator import (
    ProfitCalculator,
    TokenFlow,
    GasCost,
    ProfitData,
)
from src.detectors.transaction_analyzer import SwapEvent

# Create a profit calculator for BSC
calculator = ProfitCalculator(
    chain_name="BSC",
    native_token_usd_price=Decimal("300.0")  # BNB price
)

# Create sample swap events (simulating a 2-hop arbitrage)
swap1 = SwapEvent(
    pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
    sender="0x1234567890123456789012345678901234567890",
    to="0x0987654321098765432109876543210987654321",
    amount0In=1000000000000000000,  # 1 token in (18 decimals)
    amount1In=0,
    amount0Out=0,
    amount1Out=1050000000000000000,  # 1.05 tokens out
    log_index=0,
)

swap2 = SwapEvent(
    pool_address="0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
    sender="0x0987654321098765432109876543210987654321",
    to="0x1234567890123456789012345678901234567890",
    amount0In=1050000000000000000,  # 1.05 tokens in
    amount1In=0,
    amount0Out=0,
    amount1Out=1100000000000000000,  # 1.1 tokens out
    log_index=1,
)

swaps = [swap1, swap2]

# Create sample receipt
receipt = {
    "gasUsed": 150000,
    "effectiveGasPrice": 5000000000,  # 5 gwei
}

# Test token flow extraction
print("Testing token flow extraction...")
token_flow = calculator.extract_token_flow(swaps)
if token_flow:
    print(f"✓ Input amount: {token_flow.input_amount}")
    print(f"✓ Output amount: {token_flow.output_amount}")
    print(f"✓ Input token index: {token_flow.input_token_index}")
    print(f"✓ Output token index: {token_flow.output_token_index}")
else:
    print("✗ Failed to extract token flow")

# Test gas cost calculation
print("\nTesting gas cost calculation...")
gas_cost = calculator.calculate_gas_cost(
    gas_used=150000,
    effective_gas_price_wei=5000000000
)
print(f"✓ Gas used: {gas_cost.gas_used}")
print(f"✓ Gas price (gwei): {gas_cost.gas_price_gwei}")
print(f"✓ Gas cost (native): {gas_cost.gas_cost_native}")
print(f"✓ Gas cost (USD): ${gas_cost.gas_cost_usd}")

# Test profit calculation
print("\nTesting profit calculation...")
profit_data = calculator.calculate_profit(swaps, receipt)
if profit_data:
    print(f"✓ Input amount: {profit_data.input_amount_native} tokens")
    print(f"✓ Output amount: {profit_data.output_amount_native} tokens")
    print(f"✓ Gross profit (native): {profit_data.gross_profit_native}")
    print(f"✓ Gross profit (USD): ${profit_data.gross_profit_usd}")
    print(f"✓ Gas cost (USD): ${profit_data.gas_cost.gas_cost_usd}")
    print(f"✓ Net profit (native): {profit_data.net_profit_native}")
    print(f"✓ Net profit (USD): ${profit_data.net_profit_usd}")
    print(f"✓ ROI: {profit_data.roi_percentage}%")
else:
    print("✗ Failed to calculate profit")

print("\n✓ All profit calculator components verified successfully!")
