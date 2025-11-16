# WebSocket Client Examples

This directory contains example client implementations for connecting to the Multi-Chain Arbitrage Monitor WebSocket API.

## Prerequisites

Install the `websockets` library:

```bash
pip install websockets
```

## Usage

### Monitor Opportunities

Monitor arbitrage opportunities on BSC with minimum profit of $1000:

```bash
python examples/websocket_client.py --mode opportunities --chain 56 --min-profit 1000
```

Monitor opportunities on Polygon:

```bash
python examples/websocket_client.py --mode opportunities --chain 137 --min-profit 5000
```

### Monitor Transactions

Monitor arbitrage transactions on BSC with minimum 2 swaps:

```bash
python examples/websocket_client.py --mode transactions --chain 56 --min-swaps 2
```

Monitor only multi-hop transactions (3+ swaps):

```bash
python examples/websocket_client.py --mode transactions --chain 56 --min-swaps 3
```

### Monitor Both

Monitor both opportunities and transactions:

```bash
python examples/websocket_client.py --mode both --chain 56
```

## Command-Line Options

- `--mode`: What to monitor (`opportunities`, `transactions`, or `both`)
- `--chain`: Chain ID (56 for BSC, 137 for Polygon)
- `--min-profit`: Minimum profit in USD (for opportunities)
- `--min-swaps`: Minimum number of swaps (for transactions)
- `--uri`: WebSocket URI (default: `ws://localhost:8000/ws/v1/stream`)

## Example Output

### Opportunities

```
============================================================
Multi-Chain Arbitrage Monitor - WebSocket Client
============================================================

Connecting to ws://localhost:8000/ws/v1/stream...
✓ Connected: Connected to Multi-Chain Arbitrage Monitor WebSocket
  Connection ID: ws_1

✓ Subscribed to opportunities
  Chain: BSC
  Min Profit: $1,000.00

Waiting for opportunities...

============================================================
Opportunity #1
============================================================
Pool:       WBNB-BUSD
Address:    0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16
Profit:     $45,230.50
Imbalance:  7.82%
Block:      68286234
Detected:   2025-11-16T16:54:43.123456
============================================================
```

### Transactions

```
============================================================
Multi-Chain Arbitrage Monitor - WebSocket Client
============================================================

Connecting to ws://localhost:8000/ws/v1/stream...
✓ Connected: Connected to Multi-Chain Arbitrage Monitor WebSocket
  Connection ID: ws_2

✓ Subscribed to transactions
  Chain: BSC
  Min Swaps: 2

Waiting for transactions...

============================================================
Transaction #1
============================================================
Hash:       0x1234567890abcdef...
From:       0xabcdef1234567890...
Strategy:   3-hop
Swaps:      3
Profit:     $1,499.25
Gas Cost:   $0.75
Block:      68286235
Detected:   2025-11-16T16:54:43.123456
============================================================
```

## Stopping the Client

Press `Ctrl+C` to disconnect and exit.

## Custom Integration

You can use the example code as a starting point for your own integrations. The key steps are:

1. Connect to WebSocket endpoint
2. Wait for welcome message
3. Send subscribe message with filters
4. Listen for messages in a loop
5. Handle different message types
6. Send periodic pings to keep connection alive

See `websocket_client.py` for a complete implementation.
