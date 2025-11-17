"""
Kafka Producer - Stream CSV data vào Kafka topic
"""
from kafka import KafkaProducer
from kafka.errors import KafkaError
import pandas as pd
import json
import time
import logging
from config import KAFKA_BOOTSTRAP_SERVERS, TOPIC_NAME, CSV_PATH, STREAM_DELAY

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockNewsProducer:
    """Kafka Producer để stream tin tức cổ phiếu"""
    
    def __init__(self, bootstrap_servers, topic_name):
        self.topic_name = topic_name
        self.producer = None
        self.bootstrap_servers = bootstrap_servers
        
    def connect(self, max_retries=10, retry_delay=5):
        """Kết nối tới Kafka với retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Attempting to connect to Kafka... (Attempt {attempt + 1}/{max_retries})")
                self.producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                    max_block_ms=10000,
                    request_timeout_ms=30000,
                    acks='all',
                    retries=3
                )
                logger.info(f"✅ Connected to Kafka at {self.bootstrap_servers}")
                return True
            except KafkaError as e:
                logger.warning(f"⚠️  Connection failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("❌ Failed to connect to Kafka after all retries")
                    raise
    
    def send_message(self, message):
        """Gửi một message vào Kafka"""
        try:
            future = self.producer.send(self.topic_name, value=message)
            # Wait for confirmation
            record_metadata = future.get(timeout=10)
            return True
        except KafkaError as e:
            logger.error(f"❌ Error sending message: {e}")
            return False
    
    def stream_csv(self, csv_path, delay=2, loop=False):
        """
        Stream CSV file vào Kafka
        
        Parameters:
        -----------
        csv_path : str
            Đường dẫn file CSV
        delay : float
            Delay giữa các message (seconds)
        loop : bool
            Nếu True, sẽ stream lặp lại từ đầu khi hết file
        """
        logger.info(f"📖 Reading CSV file: {csv_path}")
        
        try:
            df = pd.read_csv(csv_path)
            logger.info(f"✓ Found {len(df)} records")
        except Exception as e:
            logger.error(f"❌ Error reading CSV: {e}")
            return
        
        # Validate columns
        required_cols = ['postID', 'stockCodes', 'title', 'description', 'date']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"❌ Missing columns: {missing_cols}")
            return
        
        logger.info(f"🚀 Starting to stream into topic '{self.topic_name}'...")
        logger.info(f"⏱️  Delay between messages: {delay}s")
        
        message_count = 0
        
        while True:
            for idx, row in df.iterrows():
                # Convert row to dict, handle NaN values
                message = row.to_dict()
                
                # Clean up NaN values
                for key, value in message.items():
                    if pd.isna(value):
                        message[key] = None
                
                # Send to Kafka
                success = self.send_message(message)
                
                if success:
                    message_count += 1
                    title_preview = message.get('title', 'N/A')[:60]
                    logger.info(f"[{message_count}] ✓ Sent: {title_preview}...")
                else:
                    logger.warning(f"[{message_count}] ⚠️  Failed to send message")
                
                # Delay để simulate realtime
                time.sleep(delay)
            
            if not loop:
                break
            
            logger.info(f"🔄 Restarting stream from beginning...")
        
        logger.info(f"✅ Completed! Sent {message_count} messages")
    
    def close(self):
        """Đóng kết nối"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("👋 Producer closed")


def main():
    """Main function"""
    logger.info("="*60)
    logger.info("🚀 KAFKA PRODUCER STARTING")
    logger.info("="*60)
    
    # Khởi tạo producer
    producer = StockNewsProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        topic_name=TOPIC_NAME
    )
    
    try:
        # Kết nối tới Kafka
        producer.connect()
        
        # Stream CSV data
        producer.stream_csv(
            csv_path=CSV_PATH,
            delay=STREAM_DELAY,
            loop=True  # Loop infinitely để simulate realtime
        )
        
    except KeyboardInterrupt:
        logger.info("\n⏹️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        producer.close()


if __name__ == "__main__":
    main()
