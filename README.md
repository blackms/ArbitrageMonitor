# Multi-Chain Arbitrage Monitor

Production-ready system to detect, track, and analyze real multi-hop arbitrage opportunities and transactions across BSC and Polygon blockchains.

## Features

- Real-time monitoring of BSC and Polygon blockchains
- Accurate arbitrage detection with zero false positives
- Pool imbalance detection using CPMM formulas
- Real profit calculation including gas costs
- REST API and WebSocket streaming
- Comprehensive monitoring and alerting

## Project Structure

```
multi-chain-arbitrage-monitor/
├── src/
│   ├── chains/          # Blockchain interaction layer
│   ├── detectors/       # Arbitrage detection and analysis
│   ├── database/        # Database management
│   ├── api/             # REST API and WebSocket server
│   ├── config/          # Configuration models
│   └── utils/           # Utility functions
├── tests/               # Test suite
├── pyproject.toml       # Poetry dependencies
└── .env.example         # Environment variables template
```

## Setup

1. Install dependencies with Poetry:
```bash
poetry install
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Set up PostgreSQL and Redis (using Docker):
```bash
docker-compose up -d postgres redis
```

## Development

Run tests:
```bash
poetry run pytest
```

Format code:
```bash
poetry run black src tests
```

Lint code:
```bash
poetry run ruff check src tests
```

## Requirements

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- BSC and Polygon RPC endpoints

## License

MIT
