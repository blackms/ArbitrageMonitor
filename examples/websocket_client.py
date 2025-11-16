"""Example WebSocket client for Multi-Chain Arbitrage Monitor"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Error: websockets library not installed")
    print("Install with: pip install websockets")
    sys.exit(1)


async def monitor_opportunities(
    uri: str = "ws://localhost:8000/ws/v1/stream",
    chain_id: int = 56,
    min_profit: float = 1000.0,
):
    """
    Monitor arbitrage opportunities via WebSocket.
    
    Args:
        uri: WebSocket URI
        chain_id: Chain ID to monitor (56=BSC, 137=Polygon)
        min_profit: Minimum profit in USD
    """
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Wait for welcome message
            welcome_msg = await websocket.recv()
            welcome = json.loads(welcome_msg)
            print(f"✓ Connected: {welcome.get('message')}")
            print(f"  Connection ID: {welcome.get('connection_id')}")
            
            # Subscribe to opportunities
            subscribe_msg = {
                "type": "subscribe",
                "channel": "opportunities",
                "filters": {
                    "chain_id": chain_id,
                    "min_profit": min_profit,
                }
            }
            
            await websocket.send(json.dumps(subscribe_msg))
            print(f"\n✓ Subscribed to opportunities")
            print(f"  Chain: {'BSC' if chain_id == 56 else 'Polygon' if chain_id == 137 else chain_id}")
            print(f"  Min Profit: ${min_profit:,.2f}")
            print("\nWaiting for opportunities...\n")
            
            # Listen for messages
            message_count = 0
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")
                
                if message_type == "subscribed":
                    print(f"✓ Subscription confirmed: {data.get('channel')}")
                
                elif message_type == "opportunity":
                    message_count += 1
                    opp = data["data"]
                    
                    print(f"\n{'='*60}")
                    print(f"Opportunity #{message_count}")
                    print(f"{'='*60}")
                    print(f"Pool:       {opp['pool_name']}")
                    print(f"Address:    {opp['pool_address']}")
                    print(f"Profit:     ${float(opp['profit_usd']):,.2f}")
                    print(f"Imbalance:  {float(opp['imbalance_pct']):.2f}%")
                    print(f"Block:      {opp['block_number']}")
                    print(f"Detected:   {opp['detected_at']}")
                    print(f"{'='*60}\n")
                
                elif message_type == "heartbeat":
                    # Send pong to keep connection alive
                    await websocket.send(json.dumps({"type": "ping"}))
                
                elif message_type == "error":
                    print(f"✗ Error: {data.get('message')}")
    
    except websockets.exceptions.ConnectionClosed:
        print("\n✗ Connection closed by server")
    except KeyboardInterrupt:
        print("\n\n✓ Disconnected by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")


async def monitor_transactions(
    uri: str = "ws://localhost:8000/ws/v1/stream",
    chain_id: int = 56,
    min_swaps: int = 2,
):
    """
    Monitor arbitrage transactions via WebSocket.
    
    Args:
        uri: WebSocket URI
        chain_id: Chain ID to monitor (56=BSC, 137=Polygon)
        min_swaps: Minimum number of swaps
    """
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Wait for welcome message
            welcome_msg = await websocket.recv()
            welcome = json.loads(welcome_msg)
            print(f"✓ Connected: {welcome.get('message')}")
            print(f"  Connection ID: {welcome.get('connection_id')}")
            
            # Subscribe to transactions
            subscribe_msg = {
                "type": "subscribe",
                "channel": "transactions",
                "filters": {
                    "chain_id": chain_id,
                    "min_swaps": min_swaps,
                }
            }
            
            await websocket.send(json.dumps(subscribe_msg))
            print(f"\n✓ Subscribed to transactions")
            print(f"  Chain: {'BSC' if chain_id == 56 else 'Polygon' if chain_id == 137 else chain_id}")
            print(f"  Min Swaps: {min_swaps}")
            print("\nWaiting for transactions...\n")
            
            # Listen for messages
            message_count = 0
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")
                
                if message_type == "subscribed":
                    print(f"✓ Subscription confirmed: {data.get('channel')}")
                
                elif message_type == "transaction":
                    message_count += 1
                    tx = data["data"]
                    
                    print(f"\n{'='*60}")
                    print(f"Transaction #{message_count}")
                    print(f"{'='*60}")
                    print(f"Hash:       {tx['tx_hash']}")
                    print(f"From:       {tx['from_address']}")
                    print(f"Strategy:   {tx['strategy']}")
                    print(f"Swaps:      {tx['swap_count']}")
                    print(f"Profit:     ${float(tx.get('profit_net_usd', 0)):,.2f}")
                    print(f"Gas Cost:   ${float(tx['gas_cost_usd']):,.2f}")
                    print(f"Block:      {tx['block_number']}")
                    print(f"Detected:   {tx['detected_at']}")
                    print(f"{'='*60}\n")
                
                elif message_type == "heartbeat":
                    # Send pong to keep connection alive
                    await websocket.send(json.dumps({"type": "ping"}))
                
                elif message_type == "error":
                    print(f"✗ Error: {data.get('message')}")
    
    except websockets.exceptions.ConnectionClosed:
        print("\n✗ Connection closed by server")
    except KeyboardInterrupt:
        print("\n\n✓ Disconnected by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")


async def monitor_both(
    uri: str = "ws://localhost:8000/ws/v1/stream",
    chain_id: int = 56,
):
    """
    Monitor both opportunities and transactions via WebSocket.
    
    Args:
        uri: WebSocket URI
        chain_id: Chain ID to monitor (56=BSC, 137=Polygon)
    """
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Wait for welcome message
            welcome_msg = await websocket.recv()
            welcome = json.loads(welcome_msg)
            print(f"✓ Connected: {welcome.get('message')}")
            print(f"  Connection ID: {welcome.get('connection_id')}")
            
            # Subscribe to opportunities
            await websocket.send(json.dumps({
                "type": "subscribe",
                "channel": "opportunities",
                "filters": {"chain_id": chain_id}
            }))
            
            # Subscribe to transactions
            await websocket.send(json.dumps({
                "type": "subscribe",
                "channel": "transactions",
                "filters": {"chain_id": chain_id}
            }))
            
            print(f"\n✓ Subscribed to opportunities and transactions")
            print(f"  Chain: {'BSC' if chain_id == 56 else 'Polygon' if chain_id == 137 else chain_id}")
            print("\nWaiting for events...\n")
            
            # Listen for messages
            opp_count = 0
            tx_count = 0
            
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")
                
                if message_type == "opportunity":
                    opp_count += 1
                    opp = data["data"]
                    print(f"[OPP #{opp_count}] {opp['pool_name']}: ${float(opp['profit_usd']):,.2f} @ {float(opp['imbalance_pct']):.2f}%")
                
                elif message_type == "transaction":
                    tx_count += 1
                    tx = data["data"]
                    print(f"[TX #{tx_count}] {tx['strategy']}: ${float(tx.get('profit_net_usd', 0)):,.2f} by {tx['from_address'][:10]}...")
                
                elif message_type == "heartbeat":
                    await websocket.send(json.dumps({"type": "ping"}))
    
    except websockets.exceptions.ConnectionClosed:
        print("\n✗ Connection closed by server")
    except KeyboardInterrupt:
        print("\n\n✓ Disconnected by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="WebSocket client for Multi-Chain Arbitrage Monitor"
    )
    parser.add_argument(
        "--mode",
        choices=["opportunities", "transactions", "both"],
        default="opportunities",
        help="What to monitor (default: opportunities)"
    )
    parser.add_argument(
        "--chain",
        type=int,
        choices=[56, 137],
        default=56,
        help="Chain ID: 56=BSC, 137=Polygon (default: 56)"
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=1000.0,
        help="Minimum profit in USD (default: 1000.0)"
    )
    parser.add_argument(
        "--min-swaps",
        type=int,
        default=2,
        help="Minimum number of swaps (default: 2)"
    )
    parser.add_argument(
        "--uri",
        default="ws://localhost:8000/ws/v1/stream",
        help="WebSocket URI (default: ws://localhost:8000/ws/v1/stream)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Multi-Chain Arbitrage Monitor - WebSocket Client")
    print("="*60 + "\n")
    
    try:
        if args.mode == "opportunities":
            asyncio.run(monitor_opportunities(
                uri=args.uri,
                chain_id=args.chain,
                min_profit=args.min_profit,
            ))
        elif args.mode == "transactions":
            asyncio.run(monitor_transactions(
                uri=args.uri,
                chain_id=args.chain,
                min_swaps=args.min_swaps,
            ))
        else:  # both
            asyncio.run(monitor_both(
                uri=args.uri,
                chain_id=args.chain,
            ))
    except KeyboardInterrupt:
        print("\n✓ Exiting...")


if __name__ == "__main__":
    main()
