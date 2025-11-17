"""
FastAPI Backend với WebSocket để stream Kafka data tới Frontend
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaConsumer
import json
import asyncio
import logging
from typing import Set
from config import KAFKA_BOOTSTRAP_SERVERS, TOPIC_NAME

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Stock News Streaming API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lưu danh sách active WebSocket connections
active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Quản lý WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.kafka_consumer = None
        self.consumer_task = None
    
    async def connect(self, websocket: WebSocket):
        """Thêm WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"✅ Client connected. Total: {len(self.active_connections)}")
        
        # Start Kafka consumer nếu chưa có
        if self.consumer_task is None or self.consumer_task.done():
            self.consumer_task = asyncio.create_task(self.consume_kafka())
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"👋 Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Gửi message tới tất cả clients"""
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ Error sending to client: {e}")
                disconnected.add(connection)
        
        # Remove failed connections
        for conn in disconnected:
            self.disconnect(conn)
    
    async def consume_kafka(self):
        """Background task để consume Kafka và broadcast tới clients"""
        logger.info("🔄 Starting Kafka consumer...")
        
        try:
            # Tạo Kafka consumer
            consumer = KafkaConsumer(
                TOPIC_NAME,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='websocket-consumer-group',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                consumer_timeout_ms=1000
            )
            
            logger.info(f"✅ Kafka consumer connected to topic: {TOPIC_NAME}")
            
            while len(self.active_connections) > 0:
                # Poll messages
                records = consumer.poll(timeout_ms=1000, max_records=10)
                
                for topic_partition, messages in records.items():
                    for message in messages:
                        # Broadcast message tới tất cả clients
                        await self.broadcast(message.value)
                
                # Small delay
                await asyncio.sleep(0.1)
            
            logger.info("⏹️  No active connections, stopping consumer...")
            consumer.close()
            
        except Exception as e:
            logger.error(f"❌ Kafka consumer error: {e}")
            import traceback
            traceback.print_exc()


# Manager instance
manager = ConnectionManager()


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Stock News Streaming API",
        "active_connections": len(manager.active_connections)
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "kafka_bootstrap": KAFKA_BOOTSTRAP_SERVERS,
        "topic": TOPIC_NAME,
        "connections": len(manager.active_connections)
    }


@app.websocket("/ws/stock-news")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint để stream tin tức realtime
    
    Frontend connect tới: ws://localhost:8000/ws/stock-news
    """
    await manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive
            # Frontend có thể gửi ping message
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    """Startup event"""
    logger.info("="*60)
    logger.info("🚀 BACKEND API STARTING")
    logger.info(f"   Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"   Topic: {TOPIC_NAME}")
    logger.info("="*60)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event"""
    logger.info("👋 Shutting down API...")
    
    # Close all WebSocket connections
    for connection in manager.active_connections.copy():
        await connection.close()
    
    logger.info("✓ All connections closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
