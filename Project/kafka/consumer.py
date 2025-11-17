"""
Kafka Consumer - Lấy data từ Kafka topic
"""
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import json
import logging
from typing import Callable
from config import KAFKA_BOOTSTRAP_SERVERS, TOPIC_NAME, CONSUMER_GROUP_ID, AUTO_OFFSET_RESET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockNewsConsumer:
    """Kafka Consumer để đọc tin tức cổ phiếu"""
    
    def __init__(self, bootstrap_servers, topic_name, group_id=None):
        self.bootstrap_servers = bootstrap_servers
        self.topic_name = topic_name
        self.group_id = group_id or CONSUMER_GROUP_ID
        self.consumer = None
        
    def connect(self, max_retries=10, retry_delay=5):
        """Kết nối tới Kafka với retry logic"""
        import time
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Connecting to Kafka... (Attempt {attempt + 1}/{max_retries})")
                self.consumer = KafkaConsumer(
                    self.topic_name,
                    bootstrap_servers=self.bootstrap_servers,
                    auto_offset_reset=AUTO_OFFSET_RESET,
                    enable_auto_commit=True,
                    group_id=self.group_id,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    consumer_timeout_ms=1000,
                    max_poll_records=10
                )
                logger.info(f"✅ Connected to Kafka topic: {self.topic_name}")
                return True
            except KafkaError as e:
                logger.warning(f"⚠️  Connection failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("❌ Failed to connect after all retries")
                    raise
    
    def consume(self, callback: Callable):
        """
        Consume messages và xử lý với callback
        
        Parameters:
        -----------
        callback : Callable
            Function nhận message data làm parameter
        """
        if not self.consumer:
            raise RuntimeError("Consumer not connected. Call connect() first.")
        
        logger.info("👂 Listening for messages...")
        
        try:
            for message in self.consumer:
                try:
                    callback(message.value)
                except Exception as e:
                    logger.error(f"❌ Error processing message: {e}")
        except KeyboardInterrupt:
            logger.info("\n⏹️  Stopped by user")
        finally:
            self.close()
    
    def consume_batch(self, batch_size=10, timeout_ms=1000):
        """
        Consume messages theo batch
        
        Returns:
        --------
        list: Danh sách messages
        """
        if not self.consumer:
            raise RuntimeError("Consumer not connected. Call connect() first.")
        
        messages = []
        records = self.consumer.poll(timeout_ms=timeout_ms, max_records=batch_size)
        
        for topic_partition, records_list in records.items():
            for record in records_list:
                messages.append(record.value)
        
        return messages
    
    def close(self):
        """Đóng kết nối"""
        if self.consumer:
            self.consumer.close()
            logger.info("👋 Consumer closed")


def main():
    """Test consumer"""
    consumer = StockNewsConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        topic_name=TOPIC_NAME
    )
    
    try:
        consumer.connect()
        
        def print_message(data):
            title = data.get('title', 'N/A')[:60]
            logger.info(f"📰 Received: {title}...")
        
        consumer.consume(print_message)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
