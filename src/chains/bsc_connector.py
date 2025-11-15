"""BSC chain connector implementation"""

from typing import Any, Dict

from src.chains.connector import ChainConnector
from src.config.models import ChainConfig


class BSCConnector(ChainConnector):
    """BSC-specific blockchain connector"""

    def __init__(self, config: ChainConfig):
        """Initialize BSC connector with configuration"""
        # Validate this is BSC config
        if config.chain_id != 56:
            raise ValueError(f"Invalid chain_id for BSC: {config.chain_id}, expected 56")

        super().__init__(config)

    def get_chain_specific_config(self) -> Dict[str, Any]:
        """Get BSC-specific configuration"""
        return {
            "chain_name": "BSC",
            "chain_id": 56,
            "native_token": "BNB",
            "block_time_seconds": 3.0,
            "dex_routers": {
                "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
                "PancakeSwap V3": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
                "BiSwap": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
                "ApeSwap": "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7",
                "THENA": "0xd4ae6eCA985340Dd434D38F470aCCce4DC78D109",
            },
            "pools": {
                "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
                "WBNB-USDT": "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
            },
        }
