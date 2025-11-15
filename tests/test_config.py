"""Tests for configuration models"""

import os
from decimal import Decimal

import pytest

from src.config.models import ChainConfig, MonitorConfig, Settings


def test_chain_config_creation():
    """Test ChainConfig model creation"""
    config = ChainConfig(
        name="BSC",
        chain_id=56,
        rpc_urls=["https://bsc-dataseed.bnbchain.org"],
        block_time_seconds=3.0,
        native_token="BNB",
        native_token_usd=Decimal("300.0"),
        dex_routers={"PancakeSwap": "0x10ED43C718714eb63d5aA57B78B54704E256024E"},
        pools={"WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"},
    )

    assert config.name == "BSC"
    assert config.chain_id == 56
    assert len(config.rpc_urls) == 1
    assert config.block_time_seconds == 3.0
    assert config.native_token == "BNB"
    assert config.native_token_usd == Decimal("300.0")
    assert "PancakeSwap" in config.dex_routers
    assert "WBNB-BUSD" in config.pools


def test_monitor_config_creation():
    """Test MonitorConfig model creation"""
    config = MonitorConfig(
        database_url="postgresql://user:pass@localhost/db",
        redis_url="redis://localhost:6379",
        api_keys=["key1", "key2"],
        rate_limit_per_minute=100,
        max_websocket_connections=100,
        log_level="INFO",
    )

    assert config.database_url == "postgresql://user:pass@localhost/db"
    assert config.redis_url == "redis://localhost:6379"
    assert len(config.api_keys) == 2
    assert config.rate_limit_per_minute == 100
    assert config.max_websocket_connections == 100
    assert config.log_level == "INFO"


def test_settings_with_env_vars(monkeypatch):
    """Test Settings loading from environment variables"""
    # Set environment variables
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("BSC_RPC_PRIMARY", "https://bsc-primary.example.com")
    monkeypatch.setenv("BSC_RPC_FALLBACK", "https://bsc-fallback.example.com")
    monkeypatch.setenv("POLYGON_RPC_PRIMARY", "https://polygon-primary.example.com")
    monkeypatch.setenv("POLYGON_RPC_FALLBACK", "https://polygon-fallback.example.com")
    monkeypatch.setenv("API_KEYS", "key1,key2,key3")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "150")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.database_url == "postgresql://test:test@localhost/test"
    assert settings.redis_url == "redis://localhost:6379"
    assert settings.bsc_rpc_primary == "https://bsc-primary.example.com"
    assert settings.bsc_rpc_fallback == "https://bsc-fallback.example.com"
    assert settings.polygon_rpc_primary == "https://polygon-primary.example.com"
    assert settings.polygon_rpc_fallback == "https://polygon-fallback.example.com"
    assert settings.rate_limit_per_minute == 150
    assert settings.log_level == "DEBUG"


def test_settings_get_api_keys_list(monkeypatch):
    """Test parsing API keys from comma-separated string"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("BSC_RPC_PRIMARY", "https://bsc.example.com")
    monkeypatch.setenv("BSC_RPC_FALLBACK", "https://bsc2.example.com")
    monkeypatch.setenv("POLYGON_RPC_PRIMARY", "https://polygon.example.com")
    monkeypatch.setenv("POLYGON_RPC_FALLBACK", "https://polygon2.example.com")
    monkeypatch.setenv("API_KEYS", "key1, key2 , key3")

    settings = Settings()
    api_keys = settings.get_api_keys_list()

    assert len(api_keys) == 3
    assert api_keys == ["key1", "key2", "key3"]


def test_settings_get_bsc_config(monkeypatch):
    """Test getting BSC chain configuration"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("BSC_RPC_PRIMARY", "https://bsc-primary.example.com")
    monkeypatch.setenv("BSC_RPC_FALLBACK", "https://bsc-fallback.example.com")
    monkeypatch.setenv("POLYGON_RPC_PRIMARY", "https://polygon.example.com")
    monkeypatch.setenv("POLYGON_RPC_FALLBACK", "https://polygon2.example.com")
    monkeypatch.setenv("API_KEYS", "key1")

    settings = Settings()
    bsc_config = settings.get_bsc_config()

    assert bsc_config.name == "BSC"
    assert bsc_config.chain_id == 56
    assert len(bsc_config.rpc_urls) == 2
    assert bsc_config.rpc_urls[0] == "https://bsc-primary.example.com"
    assert bsc_config.rpc_urls[1] == "https://bsc-fallback.example.com"
    assert bsc_config.native_token == "BNB"
    assert "PancakeSwap V2" in bsc_config.dex_routers
    assert "WBNB-BUSD" in bsc_config.pools


def test_settings_get_polygon_config(monkeypatch):
    """Test getting Polygon chain configuration"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("BSC_RPC_PRIMARY", "https://bsc.example.com")
    monkeypatch.setenv("BSC_RPC_FALLBACK", "https://bsc2.example.com")
    monkeypatch.setenv("POLYGON_RPC_PRIMARY", "https://polygon-primary.example.com")
    monkeypatch.setenv("POLYGON_RPC_FALLBACK", "https://polygon-fallback.example.com")
    monkeypatch.setenv("API_KEYS", "key1")

    settings = Settings()
    polygon_config = settings.get_polygon_config()

    assert polygon_config.name == "Polygon"
    assert polygon_config.chain_id == 137
    assert len(polygon_config.rpc_urls) == 2
    assert polygon_config.rpc_urls[0] == "https://polygon-primary.example.com"
    assert polygon_config.rpc_urls[1] == "https://polygon-fallback.example.com"
    assert polygon_config.native_token == "MATIC"
    assert "QuickSwap" in polygon_config.dex_routers
    assert "WMATIC-USDC" in polygon_config.pools


def test_settings_get_monitor_config(monkeypatch):
    """Test getting monitor configuration"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("BSC_RPC_PRIMARY", "https://bsc.example.com")
    monkeypatch.setenv("BSC_RPC_FALLBACK", "https://bsc2.example.com")
    monkeypatch.setenv("POLYGON_RPC_PRIMARY", "https://polygon.example.com")
    monkeypatch.setenv("POLYGON_RPC_FALLBACK", "https://polygon2.example.com")
    monkeypatch.setenv("API_KEYS", "key1,key2")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "200")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    settings = Settings()
    monitor_config = settings.get_monitor_config()

    assert monitor_config.database_url == "postgresql://test:test@localhost/test"
    assert monitor_config.redis_url == "redis://localhost:6379"
    assert len(monitor_config.api_keys) == 2
    assert monitor_config.rate_limit_per_minute == 200
    assert monitor_config.log_level == "WARNING"
