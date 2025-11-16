"""Polygon chain connector implementation"""

from typing import Any, Dict

from src.chains.connector import ChainConnector
from src.config.models import ChainConfig


class PolygonConnector(ChainConnector):
    """Polygon-specific blockchain connector"""

    def __init__(self, config: ChainConfig):
        """Initialize Polygon connector with configuration"""
        # Validate this is Polygon config
        if config.chain_id != 137:
            raise ValueError(f"Invalid chain_id for Polygon: {config.chain_id}, expected 137")

        super().__init__(config)

    def get_chain_specific_config(self) -> Dict[str, Any]:
        """Get Polygon-specific configuration"""
        return {
            "chain_name": "Polygon",
            "chain_id": 137,
            "native_token": "MATIC",
            "block_time_seconds": 2.0,
            "dex_routers": {
                "QuickSwap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
                "SushiSwap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
                "Uniswap V3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                "Balancer": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            },
            "pools": {
                "WMATIC-USDC": "0x6e7a5FAFcec6BB1e78bAA2A0430e3B1B64B5c0D7",
                "WMATIC-USDT": "0x604229c960e5CACF2aaEAc8Be68Ac07BA9dF81c3",
            },
        }
