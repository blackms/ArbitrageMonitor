"""Transaction analyzer for detecting arbitrage transactions"""

from dataclasses import dataclass
from typing import List, Optional

import structlog
from web3 import Web3
from web3.types import TxReceipt

logger = structlog.get_logger()


@dataclass
class SwapEvent:
    """Represents a parsed Swap event from a transaction"""

    pool_address: str
    sender: str
    to: str
    amount0In: int
    amount1In: int
    amount0Out: int
    amount1Out: int
    log_index: int


class TransactionAnalyzer:
    """Analyzes transactions for arbitrage patterns"""

    # Calculate Swap event signature
    # Swap(address indexed sender, uint256 amount0In, uint256 amount1In, uint256 amount0Out, uint256 amount1Out, address indexed to)
    SWAP_EVENT_SIGNATURE = Web3.keccak(
        text="Swap(address,uint256,uint256,uint256,uint256,address)"
    ).hex()

    def __init__(self, chain_name: str, dex_routers: dict):
        """
        Initialize transaction analyzer

        Args:
            chain_name: Name of the blockchain (e.g., "BSC", "Polygon")
            dex_routers: Dictionary of DEX router names to addresses
        """
        self.chain_name = chain_name
        self.dex_routers = dex_routers
        # Normalize router addresses to checksum format
        self.router_addresses = {
            Web3.to_checksum_address(addr) for addr in dex_routers.values()
        }

    def count_swap_events(self, receipt: TxReceipt) -> int:
        """
        Count Swap events in a transaction receipt by filtering on event signature

        Only counts events that match the Swap event signature, excluding
        Transfer, Sync, Approval, and other event types.

        Args:
            receipt: Transaction receipt containing logs

        Returns:
            Number of Swap events found
        """
        swap_count = 0

        for log in receipt.get("logs", []):
            # Check if log has topics and the first topic matches Swap signature
            topics = log.get("topics", [])
            if topics and len(topics) > 0:
                # Convert topic to hex string if it's bytes
                topic0 = topics[0].hex() if isinstance(topics[0], bytes) else topics[0]

                # Compare with Swap event signature
                if topic0 == self.SWAP_EVENT_SIGNATURE:
                    swap_count += 1

        logger.debug(
            "swap_events_counted",
            chain=self.chain_name,
            tx_hash=receipt.get("transactionHash", "").hex()
            if isinstance(receipt.get("transactionHash"), bytes)
            else receipt.get("transactionHash", ""),
            swap_count=swap_count,
            total_logs=len(receipt.get("logs", [])),
        )

        return swap_count

    def parse_swap_events(self, receipt: TxReceipt) -> List[SwapEvent]:
        """
        Parse all Swap events from a transaction receipt to extract token amounts

        Args:
            receipt: Transaction receipt containing logs

        Returns:
            List of SwapEvent objects with parsed data
        """
        swap_events = []

        for log in receipt.get("logs", []):
            topics = log.get("topics", [])
            if not topics or len(topics) == 0:
                continue

            # Convert topic to hex string if it's bytes
            topic0 = topics[0].hex() if isinstance(topics[0], bytes) else topics[0]

            # Only process Swap events
            if topic0 != self.SWAP_EVENT_SIGNATURE:
                continue

            try:
                # Extract indexed parameters from topics
                # topics[0] = event signature
                # topics[1] = sender (indexed)
                # topics[2] = to (indexed)
                sender = (
                    Web3.to_checksum_address("0x" + topics[1].hex()[-40:])
                    if isinstance(topics[1], bytes)
                    else Web3.to_checksum_address("0x" + topics[1][-40:])
                )
                to = (
                    Web3.to_checksum_address("0x" + topics[2].hex()[-40:])
                    if isinstance(topics[2], bytes)
                    else Web3.to_checksum_address("0x" + topics[2][-40:])
                )

                # Extract non-indexed parameters from data
                # data contains: amount0In, amount1In, amount0Out, amount1Out (each 32 bytes)
                data = log.get("data", "")
                if isinstance(data, bytes):
                    data = data.hex()

                # Remove '0x' prefix if present
                if data.startswith("0x"):
                    data = data[2:]

                # Each uint256 is 64 hex characters (32 bytes)
                if len(data) < 256:  # 4 * 64 = 256 hex chars
                    logger.warning(
                        "swap_event_data_too_short",
                        chain=self.chain_name,
                        data_length=len(data),
                        log_index=log.get("logIndex", -1),
                    )
                    continue

                amount0In = int(data[0:64], 16)
                amount1In = int(data[64:128], 16)
                amount0Out = int(data[128:192], 16)
                amount1Out = int(data[192:256], 16)

                # Get pool address
                pool_address = Web3.to_checksum_address(log.get("address", ""))

                swap_event = SwapEvent(
                    pool_address=pool_address,
                    sender=sender,
                    to=to,
                    amount0In=amount0In,
                    amount1In=amount1In,
                    amount0Out=amount0Out,
                    amount1Out=amount1Out,
                    log_index=log.get("logIndex", -1),
                )

                swap_events.append(swap_event)

                logger.debug(
                    "swap_event_parsed",
                    chain=self.chain_name,
                    pool=pool_address,
                    amount0In=amount0In,
                    amount1In=amount1In,
                    amount0Out=amount0Out,
                    amount1Out=amount1Out,
                    log_index=swap_event.log_index,
                )

            except Exception as e:
                logger.error(
                    "swap_event_parse_error",
                    chain=self.chain_name,
                    error=str(e),
                    log_index=log.get("logIndex", -1),
                )
                continue

        return swap_events

    def is_arbitrage(self, receipt: TxReceipt, transaction: dict) -> bool:
        """
        Determine if a transaction is an arbitrage transaction

        A transaction is classified as arbitrage if:
        1. It contains 2 or more Swap events
        2. It targets a known DEX router address
        3. It uses a recognized swap method signature

        Args:
            receipt: Transaction receipt
            transaction: Transaction data

        Returns:
            True if transaction is arbitrage, False otherwise
        """
        # Check swap count
        swap_count = self.count_swap_events(receipt)
        if swap_count < 2:
            logger.debug(
                "not_arbitrage_insufficient_swaps",
                chain=self.chain_name,
                tx_hash=receipt.get("transactionHash", "").hex()
                if isinstance(receipt.get("transactionHash"), bytes)
                else receipt.get("transactionHash", ""),
                swap_count=swap_count,
            )
            return False

        # Check if transaction targets a known DEX router
        to_address = transaction.get("to", "")
        if to_address:
            to_address = Web3.to_checksum_address(to_address)
            if to_address not in self.router_addresses:
                logger.debug(
                    "not_arbitrage_unknown_router",
                    chain=self.chain_name,
                    tx_hash=receipt.get("transactionHash", "").hex()
                    if isinstance(receipt.get("transactionHash"), bytes)
                    else receipt.get("transactionHash", ""),
                    to_address=to_address,
                )
                return False

        # Extract method signature from transaction input
        input_data = transaction.get("input", "")
        if isinstance(input_data, bytes):
            input_data = input_data.hex()

        if input_data.startswith("0x"):
            input_data = input_data[2:]

        if len(input_data) < 8:  # Method signature is 4 bytes = 8 hex chars
            logger.debug(
                "not_arbitrage_no_method_signature",
                chain=self.chain_name,
                tx_hash=receipt.get("transactionHash", "").hex()
                if isinstance(receipt.get("transactionHash"), bytes)
                else receipt.get("transactionHash", ""),
            )
            return False

        method_signature = input_data[:8]

        # Common swap method signatures (first 4 bytes of function selector)
        # swapExactTokensForTokens, swapTokensForExactTokens, etc.
        known_swap_methods = {
            "38ed1739",  # swapExactTokensForTokens
            "8803dbee",  # swapTokensForExactTokens
            "7ff36ab5",  # swapExactETHForTokens
            "18cbafe5",  # swapExactTokensForETH
            "fb3bdb41",  # swapETHForExactTokens
            "4a25d94a",  # swapTokensForExactETH
            "5c11d795",  # swapExactTokensForTokensSupportingFeeOnTransferTokens
            "b6f9de95",  # swapExactETHForTokensSupportingFeeOnTransferTokens
            "791ac947",  # swapExactTokensForETHSupportingFeeOnTransferTokens
            "472b43f3",  # swapExactAmountIn (Balancer)
            "128acb08",  # swapExactAmountOut (Balancer)
            "c04b8d59",  # exactInput (Uniswap V3)
            "09b81346",  # exactInputSingle (Uniswap V3)
            "f28c0498",  # exactOutput (Uniswap V3)
            "db3e2198",  # exactOutputSingle (Uniswap V3)
        }

        if method_signature not in known_swap_methods:
            logger.debug(
                "not_arbitrage_unknown_method",
                chain=self.chain_name,
                tx_hash=receipt.get("transactionHash", "").hex()
                if isinstance(receipt.get("transactionHash"), bytes)
                else receipt.get("transactionHash", ""),
                method_signature=method_signature,
            )
            return False

        logger.info(
            "arbitrage_detected",
            chain=self.chain_name,
            tx_hash=receipt.get("transactionHash", "").hex()
            if isinstance(receipt.get("transactionHash"), bytes)
            else receipt.get("transactionHash", ""),
            swap_count=swap_count,
            router=to_address,
            method=method_signature,
        )

        return True
