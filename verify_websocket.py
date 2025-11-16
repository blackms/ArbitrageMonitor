"""Verification script for WebSocket streaming functionality"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal

from src.api.websocket import (
    SubscriptionFilter,
    WebSocketConnection,
    WebSocketManager,
)


class MockWebSocket:
    """Mock WebSocket for testing"""

    def __init__(self):
        self.messages = []
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, message: str):
        self.messages.append(json.loads(message))

    async def receive_text(self):
        await asyncio.sleep(0.1)
        return json.dumps({"type": "ping"})

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True


async def test_subscription_filter():
    """Test subscription filter matching"""
    print("\n=== Testing Subscription Filter ===")

    # Create filter for BSC opportunities with min profit $1000
    filter1 = SubscriptionFilter(
        channel="opportunities",
        chain_id=56,
        min_profit=1000.0,
    )

    # Test matching data
    data1 = {
        "chain_id": 56,
        "profit_usd": Decimal("5000.50"),
        "pool_name": "WBNB-BUSD",
    }

    assert filter1.matches(data1), "Should match BSC opportunity with profit > $1000"
    print("✓ Filter matches BSC opportunity with profit $5000")

    # Test non-matching chain
    data2 = {
        "chain_id": 137,  # Polygon
        "profit_usd": Decimal("5000.50"),
    }

    assert not filter1.matches(data2), "Should not match Polygon opportunity"
    print("✓ Filter rejects Polygon opportunity (chain_id mismatch)")

    # Test non-matching profit
    data3 = {
        "chain_id": 56,
        "profit_usd": Decimal("500.00"),  # Below min
    }

    assert not filter1.matches(data3), "Should not match opportunity with profit < $1000"
    print("✓ Filter rejects opportunity with profit $500 (below min)")

    # Test transaction filter with min_swaps
    filter2 = SubscriptionFilter(
        channel="transactions",
        min_swaps=3,
    )

    data4 = {
        "chain_id": 56,
        "swap_count": 4,
        "profit_net_usd": Decimal("1000.00"),
    }

    assert filter2.matches(data4), "Should match transaction with 4 swaps"
    print("✓ Filter matches transaction with 4 swaps (min 3)")

    data5 = {
        "chain_id": 56,
        "swap_count": 2,
    }

    assert not filter2.matches(data5), "Should not match transaction with 2 swaps"
    print("✓ Filter rejects transaction with 2 swaps (below min 3)")


async def test_websocket_connection():
    """Test WebSocket connection management"""
    print("\n=== Testing WebSocket Connection ===")

    mock_ws = MockWebSocket()
    connection = WebSocketConnection(mock_ws, "test_conn_1")

    # Test adding subscription
    subscription = SubscriptionFilter(
        channel="opportunities",
        chain_id=56,
        min_profit=1000.0,
    )

    connection.add_subscription(subscription)
    assert len(connection.subscriptions) == 1, "Should have 1 subscription"
    print("✓ Subscription added successfully")

    # Test should_receive
    data = {
        "chain_id": 56,
        "profit_usd": Decimal("2000.00"),
    }

    assert connection.should_receive("opportunities", data), "Should receive matching data"
    print("✓ Connection should receive matching opportunity")

    # Test sending message
    message = {"type": "test", "data": "hello"}
    success = await connection.send_message(message)
    assert success, "Should send message successfully"
    assert len(mock_ws.messages) == 1, "Should have 1 message"
    assert mock_ws.messages[0]["type"] == "test", "Message type should match"
    print("✓ Message sent successfully")

    # Test removing subscription
    connection.remove_subscription("opportunities")
    assert len(connection.subscriptions) == 0, "Should have 0 subscriptions"
    print("✓ Subscription removed successfully")


async def test_websocket_manager():
    """Test WebSocket manager"""
    print("\n=== Testing WebSocket Manager ===")

    manager = WebSocketManager(max_connections=2)

    # Test connection acceptance
    mock_ws1 = MockWebSocket()
    connection1 = await manager.connect(mock_ws1)
    assert connection1 is not None, "Should accept first connection"
    assert manager.get_connection_count() == 1, "Should have 1 connection"
    print("✓ First connection accepted")

    # Test connection limit
    mock_ws2 = MockWebSocket()
    connection2 = await manager.connect(mock_ws2)
    assert connection2 is not None, "Should accept second connection"
    assert manager.get_connection_count() == 2, "Should have 2 connections"
    print("✓ Second connection accepted")

    # Test at capacity
    mock_ws3 = MockWebSocket()
    connection3 = await manager.connect(mock_ws3)
    assert connection3 is None, "Should reject third connection (at capacity)"
    # Note: The websocket_endpoint function handles closing, not the manager
    print("✓ Third connection rejected (at capacity)")

    # Test disconnection
    await manager.disconnect(connection1.connection_id)
    assert manager.get_connection_count() == 1, "Should have 1 connection after disconnect"
    print("✓ Connection disconnected successfully")

    # Test message handling - subscribe
    subscribe_msg = json.dumps({
        "type": "subscribe",
        "channel": "opportunities",
        "filters": {
            "chain_id": 56,
            "min_profit": 1000.0,
        }
    })

    await manager.handle_message(connection2, subscribe_msg)
    assert len(connection2.subscriptions) == 1, "Should have 1 subscription"
    assert len(mock_ws2.messages) > 0, "Should receive subscribed confirmation"
    print("✓ Subscribe message handled successfully")

    # Test message handling - unsubscribe
    unsubscribe_msg = json.dumps({
        "type": "unsubscribe",
        "channel": "opportunities",
    })

    await manager.handle_message(connection2, unsubscribe_msg)
    assert len(connection2.subscriptions) == 0, "Should have 0 subscriptions"
    print("✓ Unsubscribe message handled successfully")

    # Test broadcasting
    # Add subscription back
    connection2.add_subscription(SubscriptionFilter(
        channel="opportunities",
        chain_id=56,
    ))

    # Queue opportunity for broadcast
    opportunity_data = {
        "chain_id": 56,
        "pool_name": "WBNB-BUSD",
        "profit_usd": 5000.0,
        "imbalance_pct": 7.5,
    }

    await manager.broadcast_opportunity(opportunity_data)
    print("✓ Opportunity queued for broadcast")

    # Queue transaction for broadcast
    transaction_data = {
        "chain_id": 56,
        "tx_hash": "0x123...",
        "swap_count": 3,
        "profit_net_usd": 1500.0,
    }

    await manager.broadcast_transaction(transaction_data)
    print("✓ Transaction queued for broadcast")


async def test_broadcast_filtering():
    """Test broadcast filtering logic"""
    print("\n=== Testing Broadcast Filtering ===")

    manager = WebSocketManager(max_connections=10)

    # Create connections with different filters
    mock_ws1 = MockWebSocket()
    conn1 = await manager.connect(mock_ws1)
    conn1.add_subscription(SubscriptionFilter(
        channel="opportunities",
        chain_id=56,  # BSC only
    ))

    mock_ws2 = MockWebSocket()
    conn2 = await manager.connect(mock_ws2)
    conn2.add_subscription(SubscriptionFilter(
        channel="opportunities",
        chain_id=137,  # Polygon only
    ))

    mock_ws3 = MockWebSocket()
    conn3 = await manager.connect(mock_ws3)
    conn3.add_subscription(SubscriptionFilter(
        channel="opportunities",
        min_profit=10000.0,  # High profit only
    ))

    # Test BSC opportunity
    bsc_opp = {
        "chain_id": 56,
        "profit_usd": 5000.0,
    }

    assert conn1.should_receive("opportunities", bsc_opp), "Conn1 should receive BSC"
    assert not conn2.should_receive("opportunities", bsc_opp), "Conn2 should not receive BSC"
    assert not conn3.should_receive("opportunities", bsc_opp), "Conn3 should not receive (profit too low)"
    print("✓ BSC opportunity filtered correctly")

    # Test Polygon opportunity with high profit
    polygon_opp = {
        "chain_id": 137,
        "profit_usd": 15000.0,
    }

    assert not conn1.should_receive("opportunities", polygon_opp), "Conn1 should not receive Polygon"
    assert conn2.should_receive("opportunities", polygon_opp), "Conn2 should receive Polygon"
    assert conn3.should_receive("opportunities", polygon_opp), "Conn3 should receive (high profit)"
    print("✓ Polygon high-profit opportunity filtered correctly")

    # Test transaction filtering
    conn1.add_subscription(SubscriptionFilter(
        channel="transactions",
        min_swaps=3,
    ))

    tx_2hop = {
        "chain_id": 56,
        "swap_count": 2,
    }

    tx_4hop = {
        "chain_id": 56,
        "swap_count": 4,
    }

    assert not conn1.should_receive("transactions", tx_2hop), "Should not receive 2-hop"
    assert conn1.should_receive("transactions", tx_4hop), "Should receive 4-hop"
    print("✓ Transaction swap count filtered correctly")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("WebSocket Streaming Verification")
    print("=" * 60)

    try:
        await test_subscription_filter()
        await test_websocket_connection()
        await test_websocket_manager()
        await test_broadcast_filtering()

        print("\n" + "=" * 60)
        print("✓ All WebSocket tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
