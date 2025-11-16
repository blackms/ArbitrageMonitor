"""WebSocket server for real-time streaming of opportunities and transactions"""

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from src.monitoring import metrics

logger = structlog.get_logger()


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal and datetime objects"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class SubscriptionFilter:
    """Filter for WebSocket subscriptions"""

    def __init__(
        self,
        channel: str,
        chain_id: Optional[int] = None,
        min_profit: Optional[float] = None,
        max_profit: Optional[float] = None,
        min_swaps: Optional[int] = None,
    ):
        """
        Initialize subscription filter.
        
        Args:
            channel: Channel name ("opportunities" or "transactions")
            chain_id: Optional chain ID filter
            min_profit: Optional minimum profit filter (USD)
            max_profit: Optional maximum profit filter (USD)
            min_swaps: Optional minimum swap count filter (for transactions)
        """
        self.channel = channel
        self.chain_id = chain_id
        self.min_profit = min_profit
        self.max_profit = max_profit
        self.min_swaps = min_swaps

    def matches(self, data: Dict[str, Any]) -> bool:
        """
        Check if data matches this filter.
        
        Args:
            data: Data dictionary to check
            
        Returns:
            True if data matches filter, False otherwise
        """
        # Check chain_id filter
        if self.chain_id is not None and data.get("chain_id") != self.chain_id:
            return False
        
        # Check profit filters
        profit = data.get("profit_usd") or data.get("profit_net_usd")
        if profit is not None:
            if isinstance(profit, Decimal):
                profit = float(profit)
            
            if self.min_profit is not None and profit < self.min_profit:
                return False
            
            if self.max_profit is not None and profit > self.max_profit:
                return False
        
        # Check min_swaps filter (for transactions)
        if self.min_swaps is not None:
            swap_count = data.get("swap_count")
            if swap_count is None or swap_count < self.min_swaps:
                return False
        
        return True


class WebSocketConnection:
    """Represents a single WebSocket connection with its subscriptions"""

    def __init__(self, websocket: WebSocket, connection_id: str):
        """
        Initialize WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
            connection_id: Unique connection identifier
        """
        self.websocket = websocket
        self.connection_id = connection_id
        self.subscriptions: List[SubscriptionFilter] = []
        self.last_heartbeat = datetime.utcnow()
        self._logger = logger.bind(
            component="websocket_connection",
            connection_id=connection_id,
        )

    def add_subscription(self, subscription: SubscriptionFilter) -> None:
        """Add a subscription filter"""
        self.subscriptions.append(subscription)
        self._logger.info(
            "subscription_added",
            channel=subscription.channel,
            chain_id=subscription.chain_id,
            min_profit=subscription.min_profit,
            max_profit=subscription.max_profit,
            min_swaps=subscription.min_swaps,
        )

    def remove_subscription(self, channel: str) -> None:
        """Remove subscriptions for a specific channel"""
        original_count = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s.channel != channel]
        removed_count = original_count - len(self.subscriptions)
        
        if removed_count > 0:
            self._logger.info(
                "subscription_removed",
                channel=channel,
                removed_count=removed_count,
            )

    def should_receive(self, channel: str, data: Dict[str, Any]) -> bool:
        """
        Check if this connection should receive data for a channel.
        
        Args:
            channel: Channel name
            data: Data to check against filters
            
        Returns:
            True if connection has matching subscription, False otherwise
        """
        for subscription in self.subscriptions:
            if subscription.channel == channel and subscription.matches(data):
                return True
        return False

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send message to WebSocket client.
        
        Args:
            message: Message dictionary to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            message_json = json.dumps(message, cls=DecimalEncoder)
            await self.websocket.send_text(message_json)
            return True
        except Exception as e:
            self._logger.error(
                "send_message_failed",
                error=str(e),
            )
            return False


class WebSocketManager:
    """
    Manages WebSocket connections and message broadcasting.
    
    Handles connection lifecycle, subscription management, and message routing.
    """

    def __init__(self, max_connections: int = 100):
        """
        Initialize WebSocket manager.
        
        Args:
            max_connections: Maximum number of concurrent connections (default 100)
        """
        self.max_connections = max_connections
        self.connections: Dict[str, WebSocketConnection] = {}
        self._connection_counter = 0
        self._logger = logger.bind(component="websocket_manager")
        
        # Message queues for broadcasting
        self.opportunity_queue: asyncio.Queue = asyncio.Queue()
        self.transaction_queue: asyncio.Queue = asyncio.Queue()
        
        # Background tasks
        self._broadcast_tasks: List[asyncio.Task] = []
        self._heartbeat_task: Optional[asyncio.Task] = None

    def get_connection_count(self) -> int:
        """Get current number of active connections"""
        return len(self.connections)

    def is_at_capacity(self) -> bool:
        """Check if at maximum connection capacity"""
        return self.get_connection_count() >= self.max_connections

    async def connect(self, websocket: WebSocket) -> Optional[WebSocketConnection]:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
            
        Returns:
            WebSocketConnection if accepted, None if at capacity
        """
        if self.is_at_capacity():
            self._logger.warning(
                "connection_rejected_capacity",
                current_connections=self.get_connection_count(),
                max_connections=self.max_connections,
            )
            return None
        
        await websocket.accept()
        
        self._connection_counter += 1
        connection_id = f"ws_{self._connection_counter}"
        
        connection = WebSocketConnection(websocket, connection_id)
        self.connections[connection_id] = connection
        
        # Update metrics
        metrics.websocket_connections_active.set(self.get_connection_count())
        
        self._logger.info(
            "connection_accepted",
            connection_id=connection_id,
            total_connections=self.get_connection_count(),
        )
        
        return connection

    async def disconnect(self, connection_id: str) -> None:
        """
        Disconnect and remove a WebSocket connection.
        
        Args:
            connection_id: Connection identifier
        """
        if connection_id in self.connections:
            del self.connections[connection_id]
            
            # Update metrics
            metrics.websocket_connections_active.set(self.get_connection_count())
            
            self._logger.info(
                "connection_disconnected",
                connection_id=connection_id,
                remaining_connections=self.get_connection_count(),
            )

    async def handle_message(
        self,
        connection: WebSocketConnection,
        message: str,
    ) -> None:
        """
        Handle incoming message from WebSocket client.
        
        Args:
            connection: WebSocket connection
            message: Message string from client
        """
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "subscribe":
                await self._handle_subscribe(connection, data)
            elif message_type == "unsubscribe":
                await self._handle_unsubscribe(connection, data)
            elif message_type == "ping":
                await self._handle_ping(connection)
            else:
                await connection.send_message({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}",
                })
        
        except json.JSONDecodeError:
            await connection.send_message({
                "type": "error",
                "message": "Invalid JSON",
            })
        except Exception as e:
            self._logger.error(
                "message_handling_error",
                connection_id=connection.connection_id,
                error=str(e),
            )
            await connection.send_message({
                "type": "error",
                "message": "Internal error",
            })

    async def _handle_subscribe(
        self,
        connection: WebSocketConnection,
        data: Dict[str, Any],
    ) -> None:
        """Handle subscribe message"""
        channel = data.get("channel")
        
        if channel not in ["opportunities", "transactions"]:
            await connection.send_message({
                "type": "error",
                "message": f"Invalid channel: {channel}. Must be 'opportunities' or 'transactions'",
            })
            return
        
        # Extract filters
        filters = data.get("filters", {})
        subscription = SubscriptionFilter(
            channel=channel,
            chain_id=filters.get("chain_id"),
            min_profit=filters.get("min_profit"),
            max_profit=filters.get("max_profit"),
            min_swaps=filters.get("min_swaps"),
        )
        
        connection.add_subscription(subscription)
        
        await connection.send_message({
            "type": "subscribed",
            "channel": channel,
            "filters": filters,
        })

    async def _handle_unsubscribe(
        self,
        connection: WebSocketConnection,
        data: Dict[str, Any],
    ) -> None:
        """Handle unsubscribe message"""
        channel = data.get("channel")
        
        if not channel:
            await connection.send_message({
                "type": "error",
                "message": "Channel is required for unsubscribe",
            })
            return
        
        connection.remove_subscription(channel)
        
        await connection.send_message({
            "type": "unsubscribed",
            "channel": channel,
        })

    async def _handle_ping(self, connection: WebSocketConnection) -> None:
        """Handle ping message (heartbeat)"""
        connection.last_heartbeat = datetime.utcnow()
        await connection.send_message({
            "type": "pong",
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def broadcast_opportunity(self, opportunity_data: Dict[str, Any]) -> None:
        """
        Queue opportunity for broadcasting to subscribed clients.
        
        Args:
            opportunity_data: Opportunity data dictionary
        """
        await self.opportunity_queue.put(opportunity_data)

    async def broadcast_transaction(self, transaction_data: Dict[str, Any]) -> None:
        """
        Queue transaction for broadcasting to subscribed clients.
        
        Args:
            transaction_data: Transaction data dictionary
        """
        await self.transaction_queue.put(transaction_data)

    async def _broadcast_opportunities_loop(self) -> None:
        """Background task to broadcast opportunities from queue"""
        self._logger.info("opportunity_broadcast_loop_started")
        
        try:
            while True:
                opportunity_data = await self.opportunity_queue.get()
                
                message = {
                    "type": "opportunity",
                    "data": opportunity_data,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
                # Broadcast to matching connections
                broadcast_count = 0
                for connection in list(self.connections.values()):
                    if connection.should_receive("opportunities", opportunity_data):
                        success = await connection.send_message(message)
                        if success:
                            broadcast_count += 1
                
                if broadcast_count > 0:
                    # Update metrics
                    metrics.websocket_messages_sent.labels(message_type="opportunity").inc(broadcast_count)
                    
                    self._logger.debug(
                        "opportunity_broadcasted",
                        broadcast_count=broadcast_count,
                        chain_id=opportunity_data.get("chain_id"),
                        profit_usd=opportunity_data.get("profit_usd"),
                    )
        
        except asyncio.CancelledError:
            self._logger.info("opportunity_broadcast_loop_cancelled")
        except Exception as e:
            self._logger.error(
                "opportunity_broadcast_loop_error",
                error=str(e),
            )

    async def _broadcast_transactions_loop(self) -> None:
        """Background task to broadcast transactions from queue"""
        self._logger.info("transaction_broadcast_loop_started")
        
        try:
            while True:
                transaction_data = await self.transaction_queue.get()
                
                message = {
                    "type": "transaction",
                    "data": transaction_data,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
                # Broadcast to matching connections
                broadcast_count = 0
                for connection in list(self.connections.values()):
                    if connection.should_receive("transactions", transaction_data):
                        success = await connection.send_message(message)
                        if success:
                            broadcast_count += 1
                
                if broadcast_count > 0:
                    # Update metrics
                    metrics.websocket_messages_sent.labels(message_type="transaction").inc(broadcast_count)
                    
                    self._logger.debug(
                        "transaction_broadcasted",
                        broadcast_count=broadcast_count,
                        chain_id=transaction_data.get("chain_id"),
                        tx_hash=transaction_data.get("tx_hash"),
                    )
        
        except asyncio.CancelledError:
            self._logger.info("transaction_broadcast_loop_cancelled")
        except Exception as e:
            self._logger.error(
                "transaction_broadcast_loop_error",
                error=str(e),
            )

    async def _heartbeat_loop(self) -> None:
        """Background task to send periodic heartbeats"""
        self._logger.info("heartbeat_loop_started")
        
        try:
            while True:
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                
                # Send heartbeat to all connections
                for connection in list(self.connections.values()):
                    await connection.send_message({
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
        
        except asyncio.CancelledError:
            self._logger.info("heartbeat_loop_cancelled")
        except Exception as e:
            self._logger.error(
                "heartbeat_loop_error",
                error=str(e),
            )

    async def start_background_tasks(self) -> None:
        """Start background tasks for broadcasting and heartbeat"""
        self._broadcast_tasks = [
            asyncio.create_task(self._broadcast_opportunities_loop()),
            asyncio.create_task(self._broadcast_transactions_loop()),
        ]
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        self._logger.info("background_tasks_started")

    async def stop_background_tasks(self) -> None:
        """Stop all background tasks"""
        # Cancel broadcast tasks
        for task in self._broadcast_tasks:
            task.cancel()
        
        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        # Wait for tasks to complete
        all_tasks = self._broadcast_tasks + ([self._heartbeat_task] if self._heartbeat_task else [])
        await asyncio.gather(*all_tasks, return_exceptions=True)
        
        self._logger.info("background_tasks_stopped")


# Global WebSocket manager instance
ws_manager = WebSocketManager(max_connections=100)


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint handler for /ws/v1/stream.
    
    Args:
        websocket: FastAPI WebSocket instance
    """
    connection = await ws_manager.connect(websocket)
    
    if connection is None:
        # At capacity, reject connection
        await websocket.close(code=1008, reason="Server at capacity")
        return
    
    try:
        # Send welcome message
        await connection.send_message({
            "type": "connected",
            "connection_id": connection.connection_id,
            "message": "Connected to Multi-Chain Arbitrage Monitor WebSocket",
        })
        
        # Handle incoming messages
        while True:
            message = await websocket.receive_text()
            await ws_manager.handle_message(connection, message)
    
    except WebSocketDisconnect:
        logger.info(
            "websocket_disconnected",
            connection_id=connection.connection_id,
        )
    except Exception as e:
        logger.error(
            "websocket_error",
            connection_id=connection.connection_id,
            error=str(e),
        )
    finally:
        await ws_manager.disconnect(connection.connection_id)
