# 📊 Kafka Stock Data Streaming Architecture

## 🎯 Tổng quan

Hệ thống đã được tái cấu trúc để **tất cả dữ liệu stock đều đi qua Kafka**, loại bỏ việc Dashboard gọi VNStock API trực tiếp. Điều này đảm bảo:
- ✅ **Tách biệt rõ ràng** giữa data producer và consumer
- ✅ **Giảm tải API calls** từ dashboard
- ✅ **Streaming architecture chuẩn** với Kafka làm message broker
- ✅ **Dễ scale** và mở rộng

---

## 🏗️ Kiến trúc Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      KAFKA PRODUCER                             │
│                   (kafka_producer.py)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🔄 Mỗi 10 giây:                                               │
│    ├─ Fetch real-time prices (Trading API)                     │
│    └─ Send to topic: stock-prices                              │
│                                                                 │
│  🔄 Mỗi 1 phút:                                                │
│    ├─ Fetch intraday data (Quote API)                          │
│    └─ Send to topic: stock-intraday                            │
│                                                                 │
│  🔄 Mỗi 5 phút:                                                │
│    ├─ Fetch historical data (Quote API)                        │
│    ├─ Calculate technical indicators (RSI, MACD, BB, etc.)     │
│    └─ Send to topic: stock-historical                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KAFKA BROKER                               │
│                    (localhost:9092)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📡 Topics:                                                     │
│    ├─ stock-prices      : Real-time price updates              │
│    ├─ stock-historical  : Historical OHLCV + indicators        │
│    └─ stock-intraday    : Intraday minute data                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   KAFKA CONSUMERS                               │
│              (vietnam_stock_dashboard.py)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  👂 Consumer 1: stock-prices                                    │
│     └─ Update st.session_state.kafka_data                      │
│                                                                 │
│  👂 Consumer 2: stock-historical                                │
│     └─ Update st.session_state.kafka_historical                │
│                                                                 │
│  👂 Consumer 3: stock-intraday                                  │
│     └─ Update st.session_state.kafka_intraday                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DASHBOARD UI                               │
│              (vietnam_stock_dashboard.py)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📊 Hiển thị data từ Kafka session state                        │
│     ├─ Real-time prices → Metric cards                         │
│     ├─ Historical data → Technical charts                      │
│     └─ Intraday data → Live candlestick chart                  │
│                                                                 │
│  🔄 Fallback: Nếu Kafka không có data → Gọi VNStock API         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Kafka Topics Chi Tiết

### 1️⃣ **stock-prices** (Real-time Prices)
**Mục đích**: Stream giá real-time mỗi 10 giây

**Data Format**:
```json
{
  "symbol": "VCB",
  "price": 85500,
  "volume": 1234567,
  "change": 500,
  "percent_change": 0.59,
  "high": 86000,
  "low": 84500,
  "avg": 85300,
  "timestamp": "2025-11-21T14:30:00"
}
```

**Sử dụng**: Hiển thị metric cards với giá real-time

---

### 2️⃣ **stock-historical** (Historical Data + Indicators)
**Mục đích**: Stream historical OHLCV + technical indicators mỗi 5 phút

**Data Format**:
```json
{
  "symbol": "VCB",
  "period_days": 365,
  "data": [
    {
      "Date": "2025-11-21",
      "Open": 85000,
      "High": 86000,
      "Low": 84500,
      "Close": 85500,
      "Volume": 5000000,
      "SMA_20": 84800,
      "SMA_50": 83500,
      "RSI": 65.3,
      "MACD": 120.5,
      "BB_upper": 87000,
      "BB_lower": 82000,
      ...
    }
  ],
  "timestamp": "2025-11-21T14:30:00"
}
```

**Sử dụng**: 
- Main technical charts (candlestick, line, area)
- Technical indicators (RSI, MACD, Bollinger Bands)
- Performance metrics

---

### 3️⃣ **stock-intraday** (Intraday Minute Data)
**Mục đích**: Stream intraday 1-minute data mỗi 1 phút

**Data Format**:
```json
{
  "symbol": "VCB",
  "type": "intraday_ohlcv",
  "data": [
    {
      "Date": "2025-11-21T09:30:00",
      "Open": 85000,
      "High": 85200,
      "Low": 84900,
      "Close": 85100,
      "Volume": 50000
    }
  ],
  "timestamp": "2025-11-21T14:30:00"
}
```

**Sử dụng**: Live candlestick chart với animation

---

## 🚀 Cách Chạy Hệ Thống

### Bước 1: Start Kafka
```powershell
# Start Zookeeper
.\bin\windows\zookeeper-server-start.bat .\config\zookeeper.properties

# Start Kafka Broker
.\bin\windows\kafka-server-start.bat .\config\server.properties
```

### Bước 2: Start Kafka Producer
```powershell
cd "C:\Users\DELL Pre 7670\Downloads\bigdata-datamining-project\Project\kafka-streamlit"
python kafka_producer.py
```

**Output mong đợi**:
```
🚀 Vietnam Stock Data Streaming (Multi-Topic)
📊 Symbols: FPT, SSI, VCB, VHM, HPG, GAS, MSN, MWG, GVR, VIC
⏱️  Cycle Interval: 10s
📡 Real-time prices: Every 10s
📊 Historical data: Every 5 minutes
⏱️ Intraday data: Every 1 minute
──────────────────────────────────────────────────
📈 VCB: 85,500 VNĐ (+0.59%)
📈 FPT: 125,300 VNĐ (+1.20%)
...
📊 Historical data sent for VCB
⏱️ Intraday data sent for VCB
✅ Cycle completed in 3.5s
```

### Bước 3: Start Dashboard
```powershell
cd "C:\Users\DELL Pre 7670\Downloads\bigdata-datamining-project\Project\kafka-streamlit"
streamlit run vietnam_stock_dashboard.py --server.port 8510
```

Dashboard sẽ:
1. ✅ Tự động start 3 Kafka consumers (background threads)
2. ✅ Nhận data từ Kafka topics
3. ✅ Update UI real-time
4. ✅ Fallback sang VNStock API nếu Kafka không có data

---

## 🔍 Kiểm Tra Kafka Topics

### Kiểm tra messages trong topic:
```powershell
# Check stock-prices topic
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic stock-prices --from-beginning

# Check stock-historical topic
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic stock-historical --from-beginning

# Check stock-intraday topic
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic stock-intraday --from-beginning
```

### List tất cả topics:
```powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --list
```

---

## 🎨 Dashboard Features

### 1. Real-time Price Cards
- ✅ Hiển thị giá từ Kafka topic `stock-prices`
- ✅ Label: "💰 Current Price (🔴 Kafka Live)"
- ✅ Update mỗi 10 giây

### 2. Technical Charts
- ✅ Sử dụng data từ Kafka topic `stock-historical`
- ✅ Bao gồm tất cả technical indicators (RSI, MACD, BB, etc.)
- ✅ Update mỗi 5 phút

### 3. Live Intraday Chart
- ✅ Sử dụng data từ Kafka topic `stock-intraday`
- ✅ Real-time candlestick animation
- ✅ Update mỗi 1 phút

### 4. Fallback Mechanism
- ✅ Nếu Kafka không có data → Tự động gọi VNStock API
- ✅ Đảm bảo dashboard luôn hoạt động
- ✅ Label rõ ràng: "(🔴 Kafka Live)" vs "(📊 VNStock)"

---

## 📝 Code Changes Summary

### kafka_producer.py
**Thay đổi chính**:
1. ✅ Đổi tên class: `StockPriceProducer` → `StockDataProducer`
2. ✅ Thêm 3 topics: `stock-prices`, `stock-historical`, `stock-intraday`
3. ✅ Thêm function `calculate_technical_indicators()` để tính indicators
4. ✅ Thêm function `fetch_historical_data()` để fetch + tính indicators
5. ✅ Thêm function `fetch_intraday_data()` để fetch intraday data
6. ✅ Thêm logic stream theo thời gian:
   - Real-time prices: Mỗi 10s
   - Historical data: Mỗi 5 phút
   - Intraday data: Mỗi 1 phút

### vietnam_stock_dashboard.py
**Thay đổi chính**:
1. ✅ Thêm 3 session states: `kafka_historical`, `kafka_intraday`, `data_queue_*`
2. ✅ Thêm 3 consumer threads: `kafka_consumer_prices_thread`, `kafka_consumer_historical_thread`, `kafka_consumer_intraday_thread`
3. ✅ Thêm function `get_data_from_kafka()` để lấy data từ Kafka session state
4. ✅ Cập nhật `fetch_vnstock_data()`:
   - Ưu tiên lấy từ Kafka
   - Fallback sang VNStock API
5. ✅ Cập nhật `fetch_intraday_data()`:
   - Ưu tiên lấy từ Kafka
   - Fallback sang VNStock API
6. ✅ Cập nhật `create_live_intraday_chart()`:
   - Ưu tiên lấy từ Kafka
   - Fallback sang VNStock API
7. ✅ Thêm logging để debug

---

## 🔧 Troubleshooting

### Problem: Dashboard không nhận data từ Kafka
**Solution**:
1. Kiểm tra Kafka broker đang chạy: `netstat -an | findstr 9092`
2. Kiểm tra producer đang stream: Xem logs của `kafka_producer.py`
3. Kiểm tra topic có messages: Dùng `kafka-console-consumer`
4. Kiểm tra dashboard logs: Xem console của Streamlit

### Problem: Producer bị lỗi khi fetch data
**Solution**:
1. Kiểm tra VNStock API: `pip install --upgrade vnstock`
2. Kiểm tra internet connection
3. Xem logs chi tiết trong console

### Problem: Technical indicators bị NaN
**Solution**:
- ✅ Đây là bình thường cho data đầu tiên (không đủ data để tính)
- ✅ Indicators cần ít nhất 20-200 data points
- ✅ Chờ producer fetch đủ historical data

---

## 📊 Performance Optimization

### Producer Side:
- ✅ Cache data để tránh fetch lại quá nhiều
- ✅ Batch processing cho technical indicators
- ✅ Rate limiting cho API calls

### Consumer Side:
- ✅ Background threads cho Kafka consumers
- ✅ Queue-based processing để tránh block UI
- ✅ Fallback mechanism để đảm bảo availability

### Kafka Side:
- ✅ Partition topics để scale
- ✅ Retention policy để quản lý storage
- ✅ Replication factor để đảm bảo reliability

---

## 🎯 Kết Luận

Hệ thống đã được tái cấu trúc thành công với kiến trúc Kafka chuẩn:
- ✅ **Producer**: Fetch data từ VNStock, tính indicators, stream vào Kafka
- ✅ **Broker**: Kafka quản lý 3 topics với data types khác nhau
- ✅ **Consumer**: Dashboard nhận data từ Kafka, fallback sang API nếu cần
- ✅ **Separation of Concerns**: Rõ ràng giữa data fetching và data presentation
- ✅ **Scalability**: Dễ dàng thêm producers/consumers mới
- ✅ **Reliability**: Fallback mechanism đảm bảo dashboard luôn hoạt động

**Next Steps**:
1. 🔄 Thêm error handling và retry logic
2. 📊 Thêm monitoring và alerting
3. 🚀 Scale producers cho nhiều stocks
4. 💾 Persist data vào database
5. 🔐 Thêm authentication và security
