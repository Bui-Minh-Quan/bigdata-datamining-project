import logging 
from datetime import date, datetime, timedelta
import time 
import sys
import os

from database.db import get_database

# --- 1. CRAWLING IMPORTS ---
# Đảm bảo tên hàm khớp với file trong folder crawling
from crawling.news_daily_crawl import main_news_crawling
from crawling.posts_daily_crawl import main_posts_crawling

# --- 2. ETL IMPORTS ---
# Kiểm tra import summarizer (giả sử bạn đã có file này)
try:
    from etl.summarizer import run_summarization
except ImportError:
    print("⚠️ Warning: Chưa tìm thấy module 'etl.summarizer'. Bước tóm tắt có thể bị lỗi.")
    def run_summarization(date): pass 

from etl.graph_loader import save_graph
from etl.memory_attention import TRRMemoryAttention
from etl.reasoning import StockPredictor
from etl.extractor import build_daily_knowledge_graph_batch

# Danh mục đầu tư
PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

def run_full_pipeline(target_date_input):
    # --- CHUẨN HÓA NGÀY THÁNG (Quan trọng) ---
    # Tạo 2 biến: 1 cho DB (String), 1 cho Logic (Date Obj)
    if isinstance(target_date_input, str):
        try:
            target_date_str = target_date_input
            target_date_obj = datetime.strptime(target_date_input, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Lỗi: Ngày '{target_date_input}' không đúng định dạng YYYY-MM-DD")
            return
    elif isinstance(target_date_input, (date, datetime)):
        target_date_obj = target_date_input
        target_date_str = target_date_input.strftime("%Y-%m-%d")
    else:
        print("❌ Lỗi: Input ngày không hợp lệ.")
        return

    print(f"\n{'='*50}")
    print(f"🚀 BẮT ĐẦU PIPELINE NGÀY {target_date_str}")
    print(f"{'='*50}\n")
    
    # ---------------------------------------------------------
    # 1. Crawling news and posts
    # ---------------------------------------------------------
    print("📰 Bước 1: Thu thập dữ liệu từ mạng xã hội và tin tức...")
    # Crawler đã được sửa để nhận cả string lẫn date object, nhưng truyền object an toàn hơn
    main_posts_crawling(target_date_obj)
    main_news_crawling(target_date_obj)
    
    # ---------------------------------------------------------
    # 2. Summarization and Graph Construction
    # ---------------------------------------------------------
    print("\n🧠 Bước 2: Tóm tắt và xây dựng đồ thị tri thức...")
    
    # Bước này thường dùng MongoDB query string
    run_summarization()
    db = get_database()
    summ_count = db['summarized_news'].count_documents({"date": target_date_str})
    print(f"📊 Kiểm tra MongoDB: Tìm thấy {summ_count} bài báo đã tóm tắt cho ngày {target_date_str}")
    
    # Extractor dùng string cho MongoDB
    daily_graph = build_daily_knowledge_graph_batch(target_date_str)
    
    # ---------------------------------------------------------
    # 3. Integrate with historical graph from Neo4j
    # ---------------------------------------------------------
    print("\n💾 Bước 3: Lưu trữ và Tích hợp đồ thị tri thức Lịch sử")
    if daily_graph.number_of_nodes() > 0:
        save_graph(daily_graph)
    else:
        print("⚠️ Đồ thị tri thức hôm nay rỗng. Vẫn tiếp tục để lấy dữ liệu quá khứ.")
    
    # ---------------------------------------------------------
    # 4. MEMORY & ATTENTION (TRR)
    # ---------------------------------------------------------
    print("\n🔍 Bước 4: Kích hoạt TRR Memory & Attention...")
    trr = TRRMemoryAttention()
    
    # Fetch graph quá khứ (dùng string date)
    G_full = trr.fetch_historical_graph(target_date_str)
    
    # Áp dụng PageRank để lọc
    G_attention = trr.apply_attention_mechanism(G_full, PORTFOLIO_STOCKS)
    
    # Format ra text cho LLM
    graph_context = trr.format_graph_for_llm(G_attention)
    trr.close()
    
    if not graph_context:
        graph_context = "Không có sự kiện quan trọng nào trong đồ thị tri thức."
        print("   -> Context rỗng.")
    else:
        print(f"   -> Context generated ({len(graph_context)} chars).")
    
    # ---------------------------------------------------------
    # 5. Prediction
    # ---------------------------------------------------------
    print("\n🔮 Bước 5: Dự đoán xu hướng (Predictor)...")
    predictor = StockPredictor()
    results = {}
    
    print(f"\n📝 Context mẫu gửi cho LLM:\n{graph_context[:300]}...\n")

    for ticker in PORTFOLIO_STOCKS:
        print(f"--- Phân tích {ticker} ---")
        # Predictor cần string date để lấy sentiment từ MongoDB
        prediction = predictor.predict(ticker, target_date_str, graph_context)
        
        print(f"   👉 Kết quả: {prediction}\n")
        results[ticker] = prediction
        
        # Nghỉ nhẹ để tránh rate limit
        time.sleep(1)

    print(f"\n✅ HOÀN THÀNH PIPELINE NGÀY {target_date_str}")
    return results

if __name__ == "__main__":
    # Bạn có thể truyền chuỗi YYYY-MM-DD vào đây thoải mái
    run_full_pipeline("2025-11-20")