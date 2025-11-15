"""Configuration models for chain settings and monitor configuration"""

from decimal import Decimal
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainConfig(BaseSettings):
    """Configuration for a blockchain network"""

    name: str
    chain_id: int
    rpc_urls: List[str]
    block_time_seconds: float
    native_token: str
    native_token_usd: Decimal
    dex_routers: Dict[str, str] = Field(default_factory=dict)
    pools: Dict[str, str] = Field(default_factory=dict)

    model_config = SettingsConfigDict(frozen=True)


class MonitorConfig:
    """Monitor configuration"""

    def __init__(
        self,
        database_url: str,
        redis_url: str,
        api_keys: List[str],
        rate_limit_per_minute: int = 100,
        max_websocket_connections: int = 100,
        log_level: str = "INFO",
        prometheus_port: int = 9090,
    ):
        self.database_url = database_url
        self.redis_url = redis_url
        self.api_keys = api_keys
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_websocket_connections = max_websocket_connections
        self.log_level = log_level
        self.prometheus_port = prometheus_port


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # Redis
    redis_url: str = Field(alias="REDIS_URL")

    # BSC Configuration
    bsc_rpc_primary: str = Field(alias="BSC_RPC_PRIMARY")
    bsc_rpc_fallback: str = Field(alias="BSC_RPC_FALLBACK")

    # Polygon Configuration
    polygon_rpc_primary: str = Field(alias="POLYGON_RPC_PRIMARY")
    polygon_rpc_fallback: str = Field(alias="POLYGON_RPC_FALLBACK")

    # API Configuration
    api_keys: str = Field(alias="API_KEYS")
    rate_limit_per_minute: int = Field(default=100, alias="RATE_LIMIT_PER_MINUTE")
    max_websocket_connections: int = Field(default=100, alias="MAX_WEBSOCKET_CONNECTIONS")

    # Monitoring
    prometheus_port: int = Field(default=9090, alias="PROMETHEUS_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys into list"""
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]

    def get_bsc_config(self) -> ChainConfig:
        """Get BSC chain configuration"""
        return ChainConfig(
            name="BSC",
            chain_id=56,
            rpc_urls=[self.bsc_rpc_primary, self.bsc_rpc_fallback],
            block_time_seconds=3.0,
            native_token="BNB",
            native_token_usd=Decimal("300.0"),  # Should be updated from price feed
            dex_routers={
                "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
                "PancakeSwap V3": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
                "BiSwap": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
                "ApeSwap": "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7",
                "THENA": "0xd4ae6eCA985340Dd434D38F470aCCce4DC78D109",
            },
            pools={
                "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
                "WBNB-USDT": "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
            },
        )

    def get_polygon_config(self) -> ChainConfig:
        """Get Polygon chain configuration"""
        return ChainConfig(
            name="Polygon",
            chain_id=137,
            rpc_urls=[self.polygon_rpc_primary, self.polygon_rpc_fallback],
            block_time_seconds=2.0,
            native_token="MATIC",
            native_token_usd=Decimal("0.80"),  # Should be updated from price feed
            dex_routers={
                "QuickSwap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
                "SushiSwap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
                "Uniswap V3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
                "Balancer": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            },
            pools={
                "WMATIC-USDC": "0x6e7a5FAFcec6BB1e78bAA2A0430e3B1B64B5c0D7",
                "WMATIC-USDT": "0x604229c960e5CACF2aaEAc8Be68Ac07BA9dF81c3",
            },
        )

    def get_monitor_config(self) -> MonitorConfig:
        """Get monitor configuration"""
        return MonitorConfig(
            database_url=self.database_url,
            redis_url=self.redis_url,
            api_keys=self.get_api_keys_list(),
            rate_limit_per_minute=self.rate_limit_per_minute,
            max_websocket_connections=self.max_websocket_connections,
            log_level=self.log_level,
            prometheus_port=self.prometheus_port,
        )
