"""
Kafka Producer - Comprehensive Stock Data Streaming
Streams Vietnam stock prices, historical data, and intraday data to Kafka
Topics:
- stock-prices: Real-time price updates
- stock-historical: Historical OHLCV data with technical indicators
- stock-intraday: Intraday minute-by-minute data
"""

import json
import time
import sys
import os
from datetime import datetime, timedelta
from kafka import KafkaProducer
import logging
import pandas as pd
import numpy as np

# Fix Windows encoding issue
if sys.platform == 'win32':
    # Set UTF-8 encoding for Windows console
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
    # Set environment variable to suppress vnstock promo
    os.environ['VNSTOCK_DISABLE_PROMO'] = '1'

# Import vnstock after fixing encoding
from vnstock import Trading, Quote

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

class StockDataProducer:
    def __init__(self, bootstrap_servers='localhost:9092'):
        """
        Khởi tạo Kafka Producer cho tất cả stock data
        
        Args:
            bootstrap_servers: Kafka broker address
        """
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
            max_block_ms=60000,
            request_timeout_ms=30000
        )
        
        # Topics
        self.topic_prices = 'stock-prices'           # Real-time prices
        self.topic_historical = 'stock-historical'   # Historical data + indicators
        self.topic_intraday = 'stock-intraday'       # Intraday minute data
        
        # Khởi tạo Trading object
        self.trading = Trading(symbol='VN30F1M')
        logger.info(f"✅ Kafka Producer initialized")
        logger.info(f"📡 Topics: {self.topic_prices}, {self.topic_historical}, {self.topic_intraday}")
    
    def calculate_technical_indicators(self, df):
        """
        Tính toán technical indicators cho DataFrame
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with technical indicators
        """
        try:
            if df is None or df.empty:
                return df
            
            data = df.copy()
            
            # Simple Moving Averages
            data['SMA_20'] = data['Close'].rolling(window=20).mean()
            data['SMA_50'] = data['Close'].rolling(window=50).mean()
            data['SMA_200'] = data['Close'].rolling(window=200).mean()
            
            # Exponential Moving Averages
            data['EMA_12'] = data['Close'].ewm(span=12).mean()
            data['EMA_26'] = data['Close'].ewm(span=26).mean()
            
            # MACD
            data['MACD'] = data['EMA_12'] - data['EMA_26']
            data['MACD_signal'] = data['MACD'].ewm(span=9).mean()
            data['MACD_histogram'] = data['MACD'] - data['MACD_signal']
            
            # RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            # Bollinger Bands
            data['BB_middle'] = data['Close'].rolling(window=20).mean()
            bb_std = data['Close'].rolling(window=20).std()
            data['BB_upper'] = data['BB_middle'] + (bb_std * 2)
            data['BB_lower'] = data['BB_middle'] - (bb_std * 2)
            
            # Volume indicators
            data['Volume_SMA'] = data['Volume'].rolling(window=20).mean()
            data['Volume_ratio'] = data['Volume'] / data['Volume_SMA']
            
            # Volatility (ATR)
            data['High_Low'] = data['High'] - data['Low']
            data['High_Close'] = np.abs(data['High'] - data['Close'].shift())
            data['Low_Close'] = np.abs(data['Low'] - data['Close'].shift())
            data['True_Range'] = data[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
            data['ATR'] = data['True_Range'].rolling(window=14).mean()
            
            # Stochastic Oscillator
            low_14 = data['Low'].rolling(window=14).min()
            high_14 = data['High'].rolling(window=14).max()
            data['Stoch_K'] = 100 * ((data['Close'] - low_14) / (high_14 - low_14))
            data['Stoch_D'] = data['Stoch_K'].rolling(window=3).mean()
            
            return data
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return df
    
    def fetch_historical_data(self, symbol, period_days=365):
        """
        Lấy historical data với technical indicators
        
        Args:
            symbol: Stock symbol
            period_days: Number of days
            
        Returns:
            dict: Historical data with indicators
        """
        try:
            quote = Quote(symbol=symbol, source='VCI')
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Get historical data
            data = quote.history(
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                interval="1D"
            )
            
            if data.empty:
                logger.warning(f"No historical data for {symbol}")
                return None
            
            # Normalize column names
            data.columns = [col.title() for col in data.columns]
            if 'Time' in data.columns:
                data = data.rename(columns={'Time': 'Date'})
            
            # Calculate indicators
            data = self.calculate_technical_indicators(data)
            
            # Convert to JSON-serializable format
            data_dict = {
                'symbol': symbol,
                'period_days': period_days,
                'data': data.reset_index().to_dict('records'),
                'timestamp': datetime.now().isoformat()
            }
            
            return data_dict
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def fetch_intraday_data(self, symbol):
        """
        Lấy intraday data (1-minute intervals)
        
        Args:
            symbol: Stock symbol
            
        Returns:
            dict: Intraday data
        """
        try:
            quote = Quote(symbol=symbol, source='VCI')
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Get intraday 1-minute data
            data = quote.history(start=today, end=today, interval='1m')
            
            if data.empty:
                # Try getting last few hours
                data = quote.intraday(date=today, page_size=100)
                
                if data.empty:
                    return None
                
                # Convert intraday format to OHLCV
                # intraday returns: time, price, volume, match_type
                data_dict = {
                    'symbol': symbol,
                    'type': 'intraday_ticks',
                    'data': data.to_dict('records'),
                    'timestamp': datetime.now().isoformat()
                }
                
                return data_dict
            
            # Normalize column names
            data.columns = [col.title() for col in data.columns]
            if 'Time' in data.columns:
                data = data.rename(columns={'Time': 'Date'})
            
            # Convert to JSON-serializable format
            data_dict = {
                'symbol': symbol,
                'type': 'intraday_ohlcv',
                'data': data.reset_index().to_dict('records'),
                'timestamp': datetime.now().isoformat()
            }
            
            return data_dict
            
        except Exception as e:
            logger.error(f"Error fetching intraday data for {symbol}: {e}")
            return None

    
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
            logger.error(f"Error fetching stock prices: {e}")
            return None
    
    def send_to_kafka(self, topic, data):
        """Send data to specific Kafka topic"""
        try:
            if isinstance(data, dict) and 'symbol' in data:
                # Single message
                self.producer.send(topic, value=data)
            elif isinstance(data, dict):
                # Multiple messages (prices)
                for symbol, price_data in data.items():
                    self.producer.send(topic, value=price_data)
            
            self.producer.flush()
            return True
            
        except Exception as e:
            logger.error(f"❌ Kafka send error: {e}")
            return False
    
    def run_cycle(self, symbols):
        """
        Chạy 1 vòng streaming cho tất cả types of data
        
        Args:
            symbols: List of stock symbols
        """
        cycle_start = time.time()
        
        # 1. Stream real-time prices
        prices = self.fetch_stock_prices(symbols)
        if prices:
            if self.send_to_kafka(self.topic_prices, prices):
                for symbol, data in prices.items():
                    change = data['percent_change']
                    icon = "📈" if change >= 0 else "📉"
                    logger.info(f"{icon} {symbol}: {data['price']:,.0f} VNĐ ({change:+.2f}%)")
        
        # 2. Stream historical data (mỗi 5 phút)
        current_time = datetime.now()
        if not hasattr(self, '_last_historical_update'):
            self._last_historical_update = {}
        
        for symbol in symbols:
            last_update = self._last_historical_update.get(symbol, datetime.min)
            if (current_time - last_update).total_seconds() >= 300:  # 5 minutes
                historical = self.fetch_historical_data(symbol, period_days=365)
                if historical:
                    if self.send_to_kafka(self.topic_historical, historical):
                        logger.info(f"📊 Historical data sent for {symbol}")
                        self._last_historical_update[symbol] = current_time
        
        # 3. Stream intraday data (mỗi 1 phút)
        if not hasattr(self, '_last_intraday_update'):
            self._last_intraday_update = {}
        
        for symbol in symbols:
            last_update = self._last_intraday_update.get(symbol, datetime.min)
            if (current_time - last_update).total_seconds() >= 60:  # 1 minute
                intraday = self.fetch_intraday_data(symbol)
                if intraday:
                    if self.send_to_kafka(self.topic_intraday, intraday):
                        logger.info(f"⏱️ Intraday data sent for {symbol}")
                        self._last_intraday_update[symbol] = current_time
        
        cycle_duration = time.time() - cycle_start
        logger.info(f"✅ Cycle completed in {cycle_duration:.1f}s")
    
    def run(self, interval=10):
        """Run producer with comprehensive data streaming"""
        print("🚀 Vietnam Stock Data Streaming (Multi-Topic)")
        print(f"📊 Symbols: {', '.join(PORTFOLIO_STOCKS)}")
        print(f"⏱️  Cycle Interval: {interval}s")
        print(f"📡 Real-time prices: Every {interval}s")
        print(f"📊 Historical data: Every 5 minutes")
        print(f"⏱️ Intraday data: Every 1 minute")
        print("─" * 50)
        
        try:
            while True:
                self.run_cycle(PORTFOLIO_STOCKS)
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping producer...")
            self.producer.close()
            print("✅ Stopped cleanly")
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
            self.producer.close()

if __name__ == "__main__":
    producer = StockDataProducer(bootstrap_servers='localhost:9092')
    
    # Stream data every 10 seconds
    producer.run(interval=10)
