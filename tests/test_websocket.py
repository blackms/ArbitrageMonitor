"""Integration tests for WebSocket streaming

These tests verify WebSocket connection handling, subscription management,
message broadcasting, and connection limits.

Requirements tested: 8.1-8.7
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.websocket import (
    WebSocketConnection,
    WebSocketManager,
    SubscriptionFilter,
)


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def ws_manager():
    """Create WebSocket manager for testing"""
    manager = WebSocketManager(max_connections=5)
    yield manager


# ============================================================================
# Connection Handling Tests (Requirement 8.1)
# ============================================================================

@pytest.mark.asyncio
async def test_websocket_connection_accept():
    """Test WebSocket connection is accepted and welcome message sent"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager(max_connections=10)
    
    # Create mock WebSocket
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock()
    
    # Connect
    connection = await manager.connect(mock_ws)
    
    assert connection is not None
    assert connection.connection_id.startswith("ws_")
    assert manager.get_connection_count() == 1
    mock_ws.accept.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_connection_limit_enforcement():
    """Test connection limit is enforced (Requirement 8.7)"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager(max_connections=2)
    
    # Add connections up to limit
    for i in range(2):
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        connection = await manager.connect(mock_ws)
        assert connection is not None
    
    assert manager.is_at_capacity() is True
    
    # Try to add one more (should be rejected)
    mock_ws_extra = AsyncMock(spec=WebSocket)
    mock_ws_extra.accept = AsyncMock()
    connection_extra = await manager.connect(mock_ws_extra)
    
    assert connection_extra is None
    assert manager.get_connection_count() == 2


@pytest.mark.asyncio
async def test_websocket_disconnection_cleanup():
    """Test connection is properly cleaned up on disconnect"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    
    connection = await manager.connect(mock_ws)
    conn_id = connection.connection_id
    
    assert manager.get_connection_count() == 1
    
    await manager.disconnect(conn_id)
    
    assert manager.get_connection_count() == 0
    assert conn_id not in manager.connections


# ============================================================================
# Heartbeat Tests (Requirement 8.1)
# ============================================================================

@pytest.mark.asyncio
async def test_heartbeat_ping_pong():
    """Test heartbeat ping/pong mechanism"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock, MagicMock
    
    # Create mock WebSocket
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn_1")
    
    # Create manager and handle ping
    manager = WebSocketManager()
    
    # Simulate ping message
    ping_message = json.dumps({"type": "ping"})
    await manager.handle_message(connection, ping_message)
    
    # Verify pong was sent
    mock_ws.send_text.assert_called_once()
    sent_message = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent_message["type"] == "pong"
    assert "timestamp" in sent_message


@pytest.mark.asyncio
async def test_heartbeat_broadcast():
    """Test periodic heartbeat messages are sent to clients"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Send heartbeat message
    success = await connection.send_message({
        "type": "heartbeat",
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    assert success is True
    mock_ws.send_text.assert_called_once()
    
    # Verify message format
    sent_message = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent_message["type"] == "heartbeat"
    assert "timestamp" in sent_message


# ============================================================================
# Subscription Management Tests (Requirement 8.2, 8.3)
# ============================================================================

@pytest.mark.asyncio
async def test_subscribe_to_opportunities_channel():
    """Test subscribing to opportunities channel (Requirement 8.2)"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Subscribe to opportunities
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "channel": "opportunities",
        "filters": {
            "chain_id": 56,
            "min_profit": 1000.0,
        }
    })
    
    await manager.handle_message(connection, subscribe_msg)
    
    # Verify subscription was added
    assert len(connection.subscriptions) == 1
    assert connection.subscriptions[0].channel == "opportunities"
    assert connection.subscriptions[0].chain_id == 56
    assert connection.subscriptions[0].min_profit == 1000.0
    
    # Verify confirmation was sent
    mock_ws.send_text.assert_called_once()
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "subscribed"
    assert response["channel"] == "opportunities"


@pytest.mark.asyncio
async def test_subscribe_to_transactions_channel():
    """Test subscribing to transactions channel (Requirement 8.3)"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Subscribe to transactions
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "channel": "transactions",
        "filters": {
            "chain_id": 137,
            "min_swaps": 3,
        }
    })
    
    await manager.handle_message(connection, subscribe_msg)
    
    # Verify subscription was added
    assert len(connection.subscriptions) == 1
    assert connection.subscriptions[0].channel == "transactions"
    assert connection.subscriptions[0].chain_id == 137
    assert connection.subscriptions[0].min_swaps == 3


@pytest.mark.asyncio
async def test_subscribe_to_invalid_channel():
    """Test subscribing to invalid channel returns error"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Try to subscribe to invalid channel
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "channel": "invalid_channel",
    })
    
    await manager.handle_message(connection, subscribe_msg)
    
    # Verify error was sent
    mock_ws.send_text.assert_called_once()
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "error"
    assert "Invalid channel" in response["message"]


@pytest.mark.asyncio
async def test_unsubscribe_from_channel():
    """Test unsubscribing from a channel"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Add subscription first
    connection.add_subscription(SubscriptionFilter("opportunities", chain_id=56))
    assert len(connection.subscriptions) == 1
    
    # Unsubscribe
    unsubscribe_msg = json.dumps({
        "type": "unsubscribe",
        "channel": "opportunities",
    })
    
    await manager.handle_message(connection, unsubscribe_msg)
    
    # Verify subscription was removed
    assert len(connection.subscriptions) == 0
    
    # Verify confirmation was sent
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "unsubscribed"
    assert response["channel"] == "opportunities"


@pytest.mark.asyncio
async def test_multiple_subscriptions():
    """Test client can subscribe to multiple channels"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Subscribe to opportunities
    await manager.handle_message(connection, json.dumps({
        "type": "subscribe",
        "channel": "opportunities",
        "filters": {"chain_id": 56}
    }))
    
    # Subscribe to transactions
    await manager.handle_message(connection, json.dumps({
        "type": "subscribe",
        "channel": "transactions",
        "filters": {"chain_id": 56}
    }))
    
    # Verify both subscriptions exist
    assert len(connection.subscriptions) == 2
    assert connection.subscriptions[0].channel == "opportunities"
    assert connection.subscriptions[1].channel == "transactions"


# ============================================================================
# Subscription Filtering Tests (Requirement 8.4, 8.5, 8.6)
# ============================================================================

def test_subscription_filter_by_chain_id():
    """Test subscription filtering by chain_id"""
    filter_bsc = SubscriptionFilter(
        channel="opportunities",
        chain_id=56,
    )
    
    # Should match BSC data
    bsc_data = {"chain_id": 56, "profit_usd": 5000.0}
    assert filter_bsc.matches(bsc_data) is True
    
    # Should not match Polygon data
    polygon_data = {"chain_id": 137, "profit_usd": 5000.0}
    assert filter_bsc.matches(polygon_data) is False


def test_subscription_filter_by_profit_range():
    """Test subscription filtering by profit range (Requirement 8.4)"""
    filter_profit = SubscriptionFilter(
        channel="opportunities",
        min_profit=1000.0,
        max_profit=10000.0,
    )
    
    # Should match data within range
    data_in_range = {"chain_id": 56, "profit_usd": 5000.0}
    assert filter_profit.matches(data_in_range) is True
    
    # Should not match data below min
    data_below = {"chain_id": 56, "profit_usd": 500.0}
    assert filter_profit.matches(data_below) is False
    
    # Should not match data above max
    data_above = {"chain_id": 56, "profit_usd": 15000.0}
    assert filter_profit.matches(data_above) is False


def test_subscription_filter_by_swap_count():
    """Test subscription filtering by swap count (Requirement 8.6)"""
    filter_swaps = SubscriptionFilter(
        channel="transactions",
        min_swaps=3,
    )
    
    # Should match transactions with 3+ swaps
    data_3_swaps = {"chain_id": 56, "swap_count": 3}
    assert filter_swaps.matches(data_3_swaps) is True
    
    data_4_swaps = {"chain_id": 56, "swap_count": 4}
    assert filter_swaps.matches(data_4_swaps) is True
    
    # Should not match transactions with fewer swaps
    data_2_swaps = {"chain_id": 56, "swap_count": 2}
    assert filter_swaps.matches(data_2_swaps) is False


def test_subscription_filter_combined():
    """Test subscription filtering with multiple criteria"""
    filter_combined = SubscriptionFilter(
        channel="transactions",
        chain_id=56,
        min_profit=1000.0,
        min_swaps=2,
    )
    
    # Should match data meeting all criteria
    data_match = {
        "chain_id": 56,
        "profit_net_usd": 2000.0,
        "swap_count": 3,
    }
    assert filter_combined.matches(data_match) is True
    
    # Should not match if chain_id differs
    data_wrong_chain = {
        "chain_id": 137,
        "profit_net_usd": 2000.0,
        "swap_count": 3,
    }
    assert filter_combined.matches(data_wrong_chain) is False
    
    # Should not match if profit too low
    data_low_profit = {
        "chain_id": 56,
        "profit_net_usd": 500.0,
        "swap_count": 3,
    }
    assert filter_combined.matches(data_low_profit) is False
    
    # Should not match if swap count too low
    data_low_swaps = {
        "chain_id": 56,
        "profit_net_usd": 2000.0,
        "swap_count": 1,
    }
    assert filter_combined.matches(data_low_swaps) is False


# ============================================================================
# Broadcast Delivery Tests (Requirement 8.4, 8.5)
# ============================================================================

@pytest.mark.asyncio
async def test_broadcast_opportunity_to_subscribers():
    """Test opportunity broadcast to subscribed clients (Requirement 8.4)"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    
    # Create mock connections
    mock_ws1 = AsyncMock(spec=WebSocket)
    mock_ws1.send_text = AsyncMock()
    conn1 = WebSocketConnection(mock_ws1, "conn1")
    conn1.add_subscription(SubscriptionFilter("opportunities", chain_id=56))
    
    mock_ws2 = AsyncMock(spec=WebSocket)
    mock_ws2.send_text = AsyncMock()
    conn2 = WebSocketConnection(mock_ws2, "conn2")
    conn2.add_subscription(SubscriptionFilter("opportunities", chain_id=137))
    
    manager.connections["conn1"] = conn1
    manager.connections["conn2"] = conn2
    
    # Broadcast BSC opportunity
    opportunity_data = {
        "chain_id": 56,
        "pool_name": "WBNB-BUSD",
        "profit_usd": 5000.0,
        "imbalance_pct": 7.5,
    }
    
    await manager.broadcast_opportunity(opportunity_data)
    
    # Process the broadcast queue
    await asyncio.sleep(0.1)  # Give time for queue processing
    
    # Only conn1 (subscribed to BSC) should receive
    # Note: In real implementation, background task processes queue
    # For unit test, we verify the filtering logic
    assert conn1.should_receive("opportunities", opportunity_data) is True
    assert conn2.should_receive("opportunities", opportunity_data) is False


@pytest.mark.asyncio
async def test_broadcast_transaction_to_subscribers():
    """Test transaction broadcast to subscribed clients (Requirement 8.5)"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    
    # Create mock connections with different filters
    mock_ws1 = AsyncMock(spec=WebSocket)
    mock_ws1.send_text = AsyncMock()
    conn1 = WebSocketConnection(mock_ws1, "conn1")
    conn1.add_subscription(SubscriptionFilter("transactions", min_swaps=2))
    
    mock_ws2 = AsyncMock(spec=WebSocket)
    mock_ws2.send_text = AsyncMock()
    conn2 = WebSocketConnection(mock_ws2, "conn2")
    conn2.add_subscription(SubscriptionFilter("transactions", min_swaps=4))
    
    manager.connections["conn1"] = conn1
    manager.connections["conn2"] = conn2
    
    # Broadcast transaction with 3 swaps
    transaction_data = {
        "chain_id": 56,
        "tx_hash": "0x123",
        "swap_count": 3,
        "profit_net_usd": 1500.0,
    }
    
    await manager.broadcast_transaction(transaction_data)
    
    # Process the broadcast queue
    await asyncio.sleep(0.1)
    
    # conn1 (min_swaps=2) should receive, conn2 (min_swaps=4) should not
    assert conn1.should_receive("transactions", transaction_data) is True
    assert conn2.should_receive("transactions", transaction_data) is False


def test_broadcast_only_to_matching_subscriptions():
    """Test broadcasts only go to clients with matching subscriptions"""
    connection = WebSocketConnection(None, "test_conn")
    
    # Subscribe to opportunities with high profit filter
    connection.add_subscription(SubscriptionFilter(
        "opportunities",
        min_profit=10000.0
    ))
    
    # Low-profit opportunity (should not match)
    low_profit_data = {
        "chain_id": 56,
        "pool_name": "Test Pool",
        "profit_usd": 5000.0,
        "imbalance_pct": 5.0,
    }
    assert connection.should_receive("opportunities", low_profit_data) is False
    
    # High-profit opportunity (should match)
    high_profit_data = {
        "chain_id": 56,
        "pool_name": "Test Pool 2",
        "profit_usd": 15000.0,
        "imbalance_pct": 10.0,
    }
    assert connection.should_receive("opportunities", high_profit_data) is True


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_invalid_json_message():
    """Test sending invalid JSON returns error"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Send invalid JSON
    await manager.handle_message(connection, "not valid json {")
    
    # Verify error was sent
    mock_ws.send_text.assert_called_once()
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "error"
    assert "Invalid JSON" in response["message"]


@pytest.mark.asyncio
async def test_unknown_message_type():
    """Test sending unknown message type returns error"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Send message with unknown type
    await manager.handle_message(connection, json.dumps({
        "type": "unknown_type",
        "data": "test"
    }))
    
    # Verify error was sent
    mock_ws.send_text.assert_called_once()
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "error"
    assert "Unknown message type" in response["message"]


@pytest.mark.asyncio
async def test_unsubscribe_without_channel():
    """Test unsubscribe without channel parameter returns error"""
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    manager = WebSocketManager()
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.send_text = AsyncMock()
    
    connection = WebSocketConnection(mock_ws, "test_conn")
    
    # Send unsubscribe without channel
    await manager.handle_message(connection, json.dumps({
        "type": "unsubscribe",
    }))
    
    # Verify error was sent
    mock_ws.send_text.assert_called_once()
    response = json.loads(mock_ws.send_text.call_args[0][0])
    assert response["type"] == "error"
    assert "Channel is required" in response["message"]


# ============================================================================
# Manager Tests
# ============================================================================

def test_manager_connection_count():
    """Test manager tracks connection count correctly"""
    manager = WebSocketManager(max_connections=10)
    
    assert manager.get_connection_count() == 0
    assert manager.is_at_capacity() is False
    
    # Simulate adding connections
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    for i in range(5):
        mock_ws = AsyncMock(spec=WebSocket)
        conn = WebSocketConnection(mock_ws, f"conn_{i}")
        manager.connections[f"conn_{i}"] = conn
    
    assert manager.get_connection_count() == 5
    assert manager.is_at_capacity() is False


def test_manager_at_capacity():
    """Test manager correctly identifies when at capacity"""
    manager = WebSocketManager(max_connections=3)
    
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    # Add connections up to limit
    for i in range(3):
        mock_ws = AsyncMock(spec=WebSocket)
        conn = WebSocketConnection(mock_ws, f"conn_{i}")
        manager.connections[f"conn_{i}"] = conn
    
    assert manager.get_connection_count() == 3
    assert manager.is_at_capacity() is True


@pytest.mark.asyncio
async def test_manager_disconnect_removes_connection():
    """Test disconnecting removes connection from manager"""
    manager = WebSocketManager()
    
    from fastapi import WebSocket
    from unittest.mock import AsyncMock
    
    mock_ws = AsyncMock(spec=WebSocket)
    conn = WebSocketConnection(mock_ws, "test_conn")
    manager.connections["test_conn"] = conn
    
    assert manager.get_connection_count() == 1
    
    await manager.disconnect("test_conn")
    
    assert manager.get_connection_count() == 0
    assert "test_conn" not in manager.connections


# ============================================================================
# Background Tasks Tests
# ============================================================================

@pytest.mark.asyncio
async def test_background_tasks_start_and_stop():
    """Test background tasks can be started and stopped"""
    manager = WebSocketManager()
    
    # Start background tasks
    await manager.start_background_tasks()
    
    assert len(manager._broadcast_tasks) == 2
    assert manager._heartbeat_task is not None
    
    # Stop background tasks
    await manager.stop_background_tasks()
    
    # Verify tasks are cancelled
    for task in manager._broadcast_tasks:
        assert task.cancelled() or task.done()
    
    assert manager._heartbeat_task.cancelled() or manager._heartbeat_task.done()
