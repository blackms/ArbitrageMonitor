"""Profit calculator for arbitrage transactions"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

import structlog

from src.detectors.transaction_analyzer import SwapEvent

logger = structlog.get_logger()


@dataclass
class TokenFlow:
    """Represents the token flow through a swap sequence"""

    input_amount: int
    output_amount: int
    input_token_index: int  # 0 or 1, indicating which token in first pool
    output_token_index: int  # 0 or 1, indicating which token in last pool


@dataclass
class GasCost:
    """Gas cost information"""

    gas_used: int
    gas_price_wei: int
    gas_price_gwei: Decimal
    gas_cost_native: Decimal
    gas_cost_usd: Decimal


@dataclass
class ProfitData:
    """Complete profit calculation data"""

    gross_profit_native: Decimal
    gross_profit_usd: Decimal
    gas_cost: GasCost
    net_profit_native: Decimal
    net_profit_usd: Decimal
    roi_percentage: Decimal
    input_amount_native: Decimal
    output_amount_native: Decimal


class ProfitCalculator:
    """Calculates profit from arbitrage transactions"""

    def __init__(self, chain_name: str, native_token_usd_price: Decimal):
        """
        Initialize profit calculator

        Args:
            chain_name: Name of the blockchain (e.g., "BSC", "Polygon")
            native_token_usd_price: Current USD price of the native token
        """
        self.chain_name = chain_name
        self.native_token_usd_price = native_token_usd_price

    def extract_token_flow(self, swaps: List[SwapEvent]) -> Optional[TokenFlow]:
        """
        Extract token flow from a sequence of swap events

        Identifies the input amount from the first swap and output amount from
        the last swap by analyzing amount0In/amount1In and amount0Out/amount1Out.

        Args:
            swaps: List of SwapEvent objects in chronological order

        Returns:
            TokenFlow object with input and output amounts, or None if invalid
        """
        if not swaps or len(swaps) == 0:
            logger.warning(
                "extract_token_flow_empty_swaps",
                chain=self.chain_name,
            )
            return None

        # Get first swap to determine input
        first_swap = swaps[0]

        # Determine which token is being input (non-zero amountIn)
        input_amount = 0
        input_token_index = 0

        if first_swap.amount0In > 0:
            input_amount = first_swap.amount0In
            input_token_index = 0
        elif first_swap.amount1In > 0:
            input_amount = first_swap.amount1In
            input_token_index = 1
        else:
            logger.warning(
                "extract_token_flow_no_input",
                chain=self.chain_name,
                pool=first_swap.pool_address,
                log_index=first_swap.log_index,
            )
            return None

        # Get last swap to determine output
        last_swap = swaps[-1]

        # Determine which token is being output (non-zero amountOut)
        output_amount = 0
        output_token_index = 0

        if last_swap.amount0Out > 0:
            output_amount = last_swap.amount0Out
            output_token_index = 0
        elif last_swap.amount1Out > 0:
            output_amount = last_swap.amount1Out
            output_token_index = 1
        else:
            logger.warning(
                "extract_token_flow_no_output",
                chain=self.chain_name,
                pool=last_swap.pool_address,
                log_index=last_swap.log_index,
            )
            return None

        token_flow = TokenFlow(
            input_amount=input_amount,
            output_amount=output_amount,
            input_token_index=input_token_index,
            output_token_index=output_token_index,
        )

        logger.debug(
            "token_flow_extracted",
            chain=self.chain_name,
            input_amount=input_amount,
            output_amount=output_amount,
            swap_count=len(swaps),
        )

        return token_flow

    def calculate_gas_cost(
        self, gas_used: int, effective_gas_price_wei: int
    ) -> GasCost:
        """
        Calculate gas cost in native token and USD

        Args:
            gas_used: Amount of gas used by the transaction
            effective_gas_price_wei: Effective gas price in wei

        Returns:
            GasCost object with detailed gas cost information
        """
        # Calculate gas cost in wei
        gas_cost_wei = gas_used * effective_gas_price_wei

        # Convert to native token (wei to ether/matic)
        # 1 ether/matic = 10^18 wei
        gas_cost_native = Decimal(gas_cost_wei) / Decimal(10**18)

        # Convert gas price to gwei for readability
        # 1 gwei = 10^9 wei
        gas_price_gwei = Decimal(effective_gas_price_wei) / Decimal(10**9)

        # Convert to USD
        gas_cost_usd = gas_cost_native * self.native_token_usd_price

        gas_cost = GasCost(
            gas_used=gas_used,
            gas_price_wei=effective_gas_price_wei,
            gas_price_gwei=gas_price_gwei,
            gas_cost_native=gas_cost_native,
            gas_cost_usd=gas_cost_usd,
        )

        logger.debug(
            "gas_cost_calculated",
            chain=self.chain_name,
            gas_used=gas_used,
            gas_price_gwei=float(gas_price_gwei),
            gas_cost_native=float(gas_cost_native),
            gas_cost_usd=float(gas_cost_usd),
        )

        return gas_cost

    def calculate_profit(
        self, swaps: List[SwapEvent], receipt: dict
    ) -> Optional[ProfitData]:
        """
        Calculate gross and net profit from swap sequence

        Args:
            swaps: List of SwapEvent objects in chronological order
            receipt: Transaction receipt containing gas information

        Returns:
            ProfitData object with complete profit calculation, or None if invalid
        """
        # Extract token flow
        token_flow = self.extract_token_flow(swaps)
        if not token_flow:
            return None

        # Convert amounts to native token (assuming 18 decimals)
        # This is a simplification - in production, you'd need to know actual token decimals
        input_amount_native = Decimal(token_flow.input_amount) / Decimal(10**18)
        output_amount_native = Decimal(token_flow.output_amount) / Decimal(10**18)

        # Calculate gross profit in native token
        gross_profit_native = output_amount_native - input_amount_native

        # Convert to USD
        gross_profit_usd = gross_profit_native * self.native_token_usd_price

        # Calculate gas cost
        gas_used = receipt.get("gasUsed", 0)
        effective_gas_price = receipt.get("effectiveGasPrice", 0)

        gas_cost = self.calculate_gas_cost(gas_used, effective_gas_price)

        # Calculate net profit
        net_profit_native = gross_profit_native - gas_cost.gas_cost_native
        net_profit_usd = gross_profit_usd - gas_cost.gas_cost_usd

        # Calculate ROI percentage
        # ROI = (net_profit / input_amount) * 100
        if input_amount_native > 0:
            roi_percentage = (net_profit_native / input_amount_native) * Decimal(100)
        else:
            roi_percentage = Decimal(0)

        profit_data = ProfitData(
            gross_profit_native=gross_profit_native,
            gross_profit_usd=gross_profit_usd,
            gas_cost=gas_cost,
            net_profit_native=net_profit_native,
            net_profit_usd=net_profit_usd,
            roi_percentage=roi_percentage,
            input_amount_native=input_amount_native,
            output_amount_native=output_amount_native,
        )

        logger.info(
            "profit_calculated",
            chain=self.chain_name,
            gross_profit_usd=float(gross_profit_usd),
            gas_cost_usd=float(gas_cost.gas_cost_usd),
            net_profit_usd=float(net_profit_usd),
            roi_percentage=float(roi_percentage),
            swap_count=len(swaps),
        )

        return profit_data
