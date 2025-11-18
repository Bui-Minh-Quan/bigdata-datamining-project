"""
Kafka Producer - Stream realtime stock prices to Kafka
Sử dụng vnstock3 để lấy giá realtime và push vào Kafka topic
"""

import json
import time
from datetime import datetime
from kafka import KafkaProducer
from vnstock import Trading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 10 mã cổ phiếu từ portfolio
PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

class StockPriceProducer:
    def __init__(self, bootstrap_servers='localhost:9092', topic='stock-prices'):
        """
        Khởi tạo Kafka Producer cho stock prices
        
        Args:
            bootstrap_servers: Kafka broker address
            topic: Kafka topic name
        """
        self.topic = topic
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_block_ms=60000,
            request_timeout_ms=30000
        )
        
        # Khởi tạo Trading object
        self.trading = Trading(symbol='VN30F1M')
        logger.info(f"✅ Kafka Producer initialized for topic: {topic}")
    
    def fetch_stock_prices(self, symbols):
        """
        Lấy giá realtime của danh sách mã cổ phiếu
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            dict: Stock prices data
        """
        try:
            df = self.trading.price_board(symbols_list=symbols)
            
            if df is None or df.empty:
                logger.warning(f"No data returned for symbols: {symbols}")
                return None
            
            # vnstock3 returns DataFrame with multi-level columns
            # Structure: ('listing', 'symbol'), ('match', 'match_price'), etc.
            prices_data = {}
            
            for idx, row in df.iterrows():
                # Get symbol from multi-level columns
                symbol = row[('listing', 'symbol')]
                
                if symbol in symbols:
                    # Get current price and reference price
                    match_price = float(row[('match', 'match_price')])
                    ref_price = float(row[('listing', 'ref_price')])
                    
                    # Calculate change
                    change = match_price - ref_price
                    percent_change = (change / ref_price * 100) if ref_price != 0 else 0
                    
                    # Extract price data
                    prices_data[symbol] = {
                        'symbol': symbol,
                        'price': match_price,
                        'volume': int(row[('match', 'accumulated_volume')]),
                        'change': change,
                        'percent_change': percent_change,
                        'high': float(row[('match', 'highest')]),
                        'low': float(row[('match', 'lowest')]),
                        'avg': float(row[('match', 'avg_match_price')]),
                        'timestamp': datetime.now().isoformat()
                    }
            
            return prices_data
            
        except Exception as e:
            logger.error(f"Error fetching stock prices: {e}", exc_info=True)
            return None
    
    def send_to_kafka(self, data):
        """
        Gửi data lên Kafka topic
        
        Args:
            data: Dictionary containing stock price data
        """
        try:
            if data:
                for symbol, price_data in data.items():
                    self.producer.send(self.topic, value=price_data)
                    logger.info(f"📤 Sent {symbol}: {price_data['price']} VNĐ ({price_data['percent_change']}%)")
                
                self.producer.flush()
        except Exception as e:
            logger.error(f"Error sending to Kafka: {e}")
    
    def run(self, interval=5):
        """
        Chạy producer loop - fetch và push data mỗi interval giây
        
        Args:
            interval: Seconds between each fetch (default: 5s)
        """
        logger.info(f"🚀 Starting producer loop (interval: {interval}s)")
        logger.info(f"📊 Streaming stocks: {', '.join(PORTFOLIO_STOCKS)}")
        
        try:
            while True:
                prices_data = self.fetch_stock_prices(PORTFOLIO_STOCKS)
                
                if prices_data:
                    self.send_to_kafka(prices_data)
                    logger.info(f"✅ Sent {len(prices_data)} stocks to Kafka")
                else:
                    logger.warning("⚠️ No price data available")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Stopping producer...")
            self.producer.close()
            logger.info("✅ Producer closed successfully")
        except Exception as e:
            logger.error(f"❌ Producer error: {e}")
            self.producer.close()

if __name__ == "__main__":
    producer = StockPriceProducer(
        bootstrap_servers='localhost:9092',
        topic='stock-prices'
    )
    
    # Stream data every 5 seconds
    producer.run(interval=5)
