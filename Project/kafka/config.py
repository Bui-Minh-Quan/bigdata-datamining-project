"""
Kafka Configuration
"""
import os

# Kafka settings
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
TOPIC_NAME = os.getenv('TOPIC_NAME', 'stock-news')

# Producer settings
CSV_PATH = os.getenv('CSV_PATH', '../summarized_news_with_stocks_merged.csv')
STREAM_DELAY = float(os.getenv('STREAM_DELAY', '2'))  # seconds between messages

# Consumer settings
CONSUMER_GROUP_ID = 'stock-news-consumer-group'
AUTO_OFFSET_RESET = 'latest'  # 'earliest' hoặc 'latest'

# API settings
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8000'))

print(f"✓ Kafka Config loaded:")
print(f"  - Bootstrap Servers: {KAFKA_BOOTSTRAP_SERVERS}")
print(f"  - Topic: {TOPIC_NAME}")
print(f"  - CSV Path: {CSV_PATH}")
