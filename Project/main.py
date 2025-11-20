import logging 
from datetime import date, datetime, timedelta
import time 
import sys
import os
import re # Import regex để xử lý text từ LLM

from database.db import get_database

# --- 1. CRAWLING IMPORTS ---
from crawling.news_daily_crawl import main_news_crawling
from crawling.posts_daily_crawl import main_posts_crawling

# --- 2. ETL IMPORTS ---
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

def parse_llm_response(response_text):
    """
    Hàm tách chuỗi text của Gemini thành các trường dữ liệu có cấu trúc
    Input format:
    [TREND]: INCREASE
    [CONFIDENCE]: 85%
    [REASONING]: ...
    """
    if not response_text:
        return "UNKNOWN", "0%", "Không có dữ liệu phân tích"
    
    # Sử dụng Regex để bắt các pattern
    trend_match = re.search(r"\[TREND\]:\s*(.*)", response_text, re.IGNORECASE)
    conf_match = re.search(r"\[CONFIDENCE\]:\s*(.*)", response_text, re.IGNORECASE)
    
    # Reasoning thường là phần còn lại hoặc nằm trong tag
    reason_match = re.search(r"\[REASONING\]:\s*((?:.|\n)*)", response_text, re.IGNORECASE)
    
    trend = trend_match.group(1).strip().upper() if trend_match else "UNKNOWN"
    confidence = conf_match.group(1).strip() if conf_match else "0%"
    reasoning = reason_match.group(1).strip() if reason_match else response_text
    
    return trend, confidence, reasoning

def save_predictions_to_db(results, target_date_str):
    """Lưu kết quả dự đoán vào MongoDB"""
    print("\n💾 Đang lưu kết quả dự đoán vào MongoDB...")
    db = get_database()
    collection = db['stock_predictions']
    
    timestamp = datetime.now()
    count = 0
    
    for ticker, full_text in results.items():
        if not full_text: continue
        
        # Parse dữ liệu
        trend, confidence, reasoning = parse_llm_response(full_text)
        
        record = {
            "date": target_date_str,
            "symbol": ticker,
            "full_analysis": full_text, # Lưu văn bản gốc
            "trend": trend,             # INCREASE/DECREASE/SIDEWAYS
            "confidence": confidence,   # VD: 85%
            "reasoning": reasoning,     # Lý do chi tiết
            "created_at": timestamp
        }
        
        # Upsert vào MongoDB
        collection.update_one(
            {"created_at": timestamp, "symbol": ticker},
            {"$set": record},
            upsert=True
        )
        count += 1
        
    print(f"✅ Đã lưu thành công {count} dự đoán vào collection 'stock_predictions'")

def run_full_pipeline(target_date_input):
    # --- CHUẨN HÓA NGÀY THÁNG ---
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
    try:
        main_posts_crawling(target_date_obj)
        main_news_crawling(target_date_obj)
    except Exception as e:
        print(f"⚠️ Lỗi Crawling (có thể bỏ qua nếu đã có data): {e}")
    
    # ---------------------------------------------------------
    # 2. Summarization and Graph Construction
    # ---------------------------------------------------------
    print("\n🧠 Bước 2: Tóm tắt và xây dựng đồ thị tri thức...")
    
    run_summarization() 
    
    # Check data
    db = get_database()
    summ_count = db['summarized_news'].count_documents({"date": target_date_str + " 00:00:00"})
    print(f"📊 Kiểm tra MongoDB: Tìm thấy {summ_count} bài báo đã tóm tắt cho ngày {target_date_str + " 00:00:00"}")
    
    # Extractor
    # target_date_str += " 00:00:00"
    daily_graph = build_daily_knowledge_graph_batch(target_date_str + " 00:00:00")
    
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
    
    # Fetch graph quá khứ
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
        prediction = predictor.predict(ticker, target_date_str, graph_context)
        
        print(f"   👉 Kết quả: {prediction}\n")
        results[ticker] = prediction
        
        # Nghỉ nhẹ để tránh rate limit
        time.sleep(1)

    # ---------------------------------------------------------
    # 6. SAVE RESULTS TO DATABASE (NEW STEP)
    # ---------------------------------------------------------
    save_predictions_to_db(results, target_date_str)

    print(f"\n✅ HOÀN THÀNH PIPELINE NGÀY {target_date_str}")
    return results

if __name__ == "__main__":
    # Chạy thử với ngày hiện tại hoặc ngày bạn muốn test
    today = datetime.now().strftime("%Y-%m-%d")
    # run_full_pipeline("2023-11-20") # Uncomment để test ngày cũ
    run_full_pipeline(today)