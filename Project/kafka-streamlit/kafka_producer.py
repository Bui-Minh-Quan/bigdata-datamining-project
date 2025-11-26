"""
Kafka Producer - Clean Real-time Stock Price Streaming
Streams Vietnam stock prices to Kafka with clean logging
"""

import json
import time
from datetime import datetime
from kafka import KafkaProducer
from vnstock import Trading
import logging
import os

from dotenv import load_dotenv
load_dotenv()

KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'localhost:9092')

# Clean logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress unnecessary logs
logging.getLogger('kafka').setLevel(logging.WARNING)
logging.getLogger('vnstock').setLevel(logging.WARNING)

# 10 mã cổ phiếu từ portfolio
PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

class StockPriceProducer:
    def __init__(self, bootstrap_servers=KAFKA_SERVER, topic='stock-prices'):
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
            # Structure: ('listing', 'symbol'), his('match', 'match_price'), etc.
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
        """Send clean stock data to Kafka"""
        try:
            if data:
                for symbol, price_data in data.items():
                    self.producer.send(self.topic, value=price_data)
                    # Clean log format
                    price = price_data['price']
                    change = price_data['percent_change']
                    change_icon = "📈" if change >= 0 else "📉"
                    logger.info(f"{change_icon} {symbol}: {price:,.0f} VNĐ ({change:+.2f}%)")
                
                self.producer.flush()
        except Exception as e:
            logger.error(f"❌ Kafka error: {e}")
    
    def run(self, interval=5):
        """Run producer with clean output"""
        print("🚀 Vietnam Stock Price Streaming")
        print(f"📊 Symbols: {', '.join(PORTFOLIO_STOCKS)}")
        print(f"⏱️  Interval: {interval}s")
        print("─" * 50)
        
        try:
            while True:
                prices_data = self.fetch_stock_prices(PORTFOLIO_STOCKS)
                
                if prices_data:
                    self.send_to_kafka(prices_data)
                    print(f"✅ Streamed {len(prices_data)} stocks | {datetime.now().strftime('%H:%M:%S')}")
                else:
                    logger.warning("⚠️ No data available")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping producer...")
            self.producer.close()
            print("✅ Stopped cleanly")
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            self.producer.close()

if __name__ == "__main__":
    producer = StockPriceProducer(
        bootstrap_servers=KAFKA_SERVER,
        topic='stock-prices'
    )
    
    # Stream data every 10 seconds
    producer.run(interval=10)
