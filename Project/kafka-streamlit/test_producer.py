"""
Test Kafka Producer - Kiểm tra kết nối và gửi data
"""

import json
from datetime import datetime
from vnstock import Trading

print("=" * 60)
print("🔍 TESTING KAFKA PRODUCER")
print("=" * 60)

# Test 1: Import Kafka
print("\n1️⃣ Testing Kafka import...")
try:
    from kafka import KafkaProducer
    print("   ✅ kafka-python imported successfully")
except Exception as e:
    print(f"   ❌ Error importing kafka: {e}")
    exit(1)

# Test 2: vnstock API
print("\n2️⃣ Testing vnstock API...")
try:
    trading = Trading(symbol='VN30F1M')
    symbols = ['FPT', 'VCB', 'SSI']
    df = trading.price_board(symbols_list=symbols)
    
    if df is not None and not df.empty:
        print(f"   ✅ Got data for {len(df)} stocks")
        
        # Parse first stock
        first_row = df.iloc[0]
        symbol = first_row[('listing', 'symbol')]
        price = first_row[('match', 'match_price')]
        print(f"   📊 Sample: {symbol} = {price} VNĐ")
    else:
        print("   ❌ No data returned from vnstock")
        exit(1)
        
except Exception as e:
    print(f"   ❌ Error with vnstock: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 3: Kafka Producer connection
print("\n3️⃣ Testing Kafka Producer connection...")
try:
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        max_block_ms=5000,  # Timeout after 5s
        request_timeout_ms=5000
    )
    print("   ✅ Kafka Producer created successfully")
    
    # Test send
    test_data = {
        'symbol': 'TEST',
        'price': 100000,
        'timestamp': datetime.now().isoformat()
    }
    
    future = producer.send('stock-prices', value=test_data)
    record_metadata = future.get(timeout=5)
    
    print(f"   ✅ Test message sent successfully")
    print(f"   📍 Topic: {record_metadata.topic}")
    print(f"   📍 Partition: {record_metadata.partition}")
    print(f"   📍 Offset: {record_metadata.offset}")
    
    producer.close()
    
except Exception as e:
    print(f"   ❌ Kafka connection error: {e}")
    print(f"   💡 Make sure Kafka is running: docker-compose up -d")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\n🚀 You can now run: python kafka_producer.py")
