# Kỹ thuật và Công nghệ dữ liệu lớn cho Trí tuệ nhân tạo

## Hệ thống Dự đoán Xu hướng Giá Cổ phiếu dựa trên LLM và Khung suy luận Quan hệ - Thời gian (TRR)

---

## 🔗 Liên kết quan trọng (Links)

| Tài nguyên | Link |
|-----------|------|
| Source Code (GitHub) | https://github.com/Bui-Minh-Quan/bigdata-datamining-project |
| Báo cáo chi tiết (PDF) | https://github.com/Bui-Minh-Quan/bigdata-datamining-project/blob/main/Big_Data_Project.pdf |
| Video Demo & Thuyết trình | Đang cập nhật |
| Trang web Demo (Live) | Đang cập nhật |
| Slides Thuyết trình | Đang cập nhật... |

---

## 📖 Giới thiệu tổng quan

Trong kỷ nguyên Big Data, thông tin tài chính không chỉ nằm ở các con số giá cả mà ẩn chứa trong hàng ngàn bản tin, bài đăng mạng xã hội mỗi ngày. Các mô hình dự báo truyền thống thường bỏ qua nguồn dữ liệu phi cấu trúc quý giá này.

Dự án này xây dựng một hệ thống hỗ trợ ra quyết định đầu tư (Investment Decision Support System) cho thị trường chứng khoán Việt Nam (VN30). Hệ thống áp dụng phương pháp Temporal Relational Reasoning (TRR) kết hợp với Graph RAG, cho phép AI không chỉ dự báo xu hướng giá (Tăng/Giảm) mà còn suy luận nhân quả và giải thích rõ ràng.

---

## 🌟 Điểm nổi bật (Key Features)

- **Đa nguồn dữ liệu (Multi-source Ingestion)**  
  Kết hợp dữ liệu giá (Structured), tin tức FireAnt (Unstructured) và dữ liệu cảm xúc F319 (Sentiment).

- **TRR Framework**  
  Mô phỏng tư duy con người qua 4 bước:  
  Brainstorming → Memory → Attention → Reasoning.

- **Real-time Streaming**  
  Sử dụng Apache Kafka để cập nhật giá cổ phiếu theo thời gian thực.

- **Graph RAG**  
  Dùng Neo4j để lưu trữ và truy vấn chuỗi tác động.  
  Ví dụ: Giá dầu tăng → Vận tải khó khăn → HPG giảm.

- **Explainable AI**  
  Dự báo đi kèm lý do rõ ràng.

---

## 🏗️ Kiến trúc hệ thống

Hệ thống được chia thành hai pipeline chính:

### 1. Batch Pipeline (Xử lý tri thức)
- Thu thập tin tức hằng ngày  
- Tóm tắt bằng LLM  
- Trích xuất đồ thị quan hệ  
- Lưu trữ vào Neo4j  
- Khi dự báo: áp dụng Time Decay + PageRank để xây dựng ngữ cảnh

### 2. Real-time Pipeline (Xử lý thị trường)
- Kafka Producer gửi giá khớp lệnh  
- Kafka Server xử lý  
- Dashboard nhận dữ liệu và hiển thị biểu đồ nến

---

## 📂 Cấu trúc thư mục (Project Structure)

```
project/
├── .env                        # API Keys (Gemini, Neo4j, FireAnt...)
├── main.py                     # Orchestrator - Pipeline chính
│
├── database/
│   └── db.py                   # Kết nối MongoDB
│
├── crawling/
│   ├── data_preprocessing.py   # Làm sạch HTML
│   ├── news_daily_crawl.py     # Crawl tin tức
│   ├── posts_daily_crawl.py    # Crawl dữ liệu cộng đồng
│   └── data_loader.py          # Tải lịch sử giá
│
├── etl/
│   ├── llm_client.py           # Quản lý Gemini API
│   ├── prompts.py              # Prompt templates
│   ├── summarizer.py           # Tóm tắt tin tức
│   ├── extractor.py            # Trích xuất Graph
│   ├── graph_loader.py         # Lưu vào Neo4j
│   ├── memory_attention.py     # TRR Engine
│   └── reasoning.py            # Mô-đun dự đoán
│
└── frontend/
    └── vietnam_stock_dashboard.py   # Streamlit Dashboard
```

---

## 🚀 Hướng dẫn cài đặt & triển khai

### Yêu cầu
- Python 3.10+
- Docker & Docker Compose
- Gemini API Key (Google AI Studio)

### Bước 1: Khởi động hạ tầng

```
docker-compose up -d zookeeper kafka mongo neo4j
```

### Bước 2: Cài đặt thư viện

```
pip install -r requirements.txt
```

### Bước 3: Cấu hình biến môi trường `.env`

```
GEMINI_API_KEYS=["key1", "key2"]
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
MONGO_URI=mongodb://localhost:27017
FIREANT_BEARER=your_token
```

### Bước 4: Chạy hệ thống

Chạy pipeline batch:

```
python main.py
```

Chạy real-time producer:

```
python kafka_producer.py
```

Khởi động dashboard:

```
streamlit run frontend/vietnam_stock_dashboard.py
```

---

## 🛠️ Công nghệ sử dụng

- **Python**
- **LLM**: Gemini 2.0 Flash (qua LangChain)
- **Database**:  
  - MongoDB (văn bản, logs, time-series)  
  - Neo4j (Knowledge Graph)  
- **Message Queue**: Apache Kafka  
- **Data Sources**: VnStock API, FireAnt  
- **Frontend**: Streamlit, Plotly, NetworkX  

---

## 👥 Thành viên nhóm thực hiện

| Họ và tên | Vai trò | Nhiệm vụ |
|-----------|---------|----------|
| Phan Nhật Quang | AI Engineer | Thuật toán TRR, Graph RAG, Prompt Engineering, Core AI |
| Bùi Minh Quân | Data Engineer | Data Pipeline, Database, Crawling |
| Phan Quang Trường | Frontend Dev | Dashboard, Visualization, Backtesting, Kafka Streaming|

---

Made with ❤️ by Big Data Team
```
