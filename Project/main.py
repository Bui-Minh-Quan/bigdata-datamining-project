import logging 
from datetime import date, datetime, timedelta
import time 
import sys
import os
import re 
import importlib

# Thêm đường dẫn project vào path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import get_database

# --- IMPORTS ---
from crawling.news_daily_crawl import main_news_crawling
from crawling.posts_daily_crawl import main_posts_crawling
# Import Data Loader mới
from crawling.data_loader import fetch_recent_data_online

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
    """Hàm tách chuỗi text của Gemini"""
    if not response_text:
        return "UNKNOWN", "0%", "Không có dữ liệu phân tích"
    
    trend_match = re.search(r"\[TREND\]:\s*(.*)", response_text, re.IGNORECASE)
    conf_match = re.search(r"\[CONFIDENCE\]:\s*(.*)", response_text, re.IGNORECASE)
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
        trend, confidence, reasoning = parse_llm_response(full_text)
        record = {
            "date": target_date_str,
            "symbol": ticker,
            "full_analysis": full_text,
            "trend": trend,
            "confidence": confidence,
            "reasoning": reasoning,
            "created_at": timestamp
        }
        collection.update_one(
            {"date": target_date_str, "symbol": ticker},
            {"$set": record},
            upsert=True
        )
        count += 1
    print(f"✅ Đã lưu thành công {count} dự đoán vào collection 'stock_predictions'")

# --- HÀM CHẠY PIPELINE CHÍNH ---
def run_full_pipeline(target_date_input=None, progress_callback=None):
    """
    Chạy toàn bộ quy trình phân tích.
    progress_callback: Hàm callback để cập nhật tiến độ lên UI (optional)
    """
    # Nếu không truyền ngày, mặc định là hôm nay
    if target_date_input is None:
        target_date_input = datetime.now().strftime("%Y-%m-%d")

    # Chuẩn hóa ngày tháng
    if isinstance(target_date_input, str):
        try:
            target_date_str = target_date_input
            target_date_obj = datetime.strptime(target_date_input, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "message": "Ngày không hợp lệ"}
    else:
        target_date_obj = target_date_input
        target_date_str = target_date_input.strftime("%Y-%m-%d")

    def update_status(msg, percent):
        print(msg)
        if progress_callback: progress_callback(msg, percent)

    print(f"\n{'='*50}")
    print(f"🚀 BẮT ĐẦU PIPELINE NGÀY {target_date_str}")
    print(f"{'='*50}\n")
    
    # BƯỚC 0: CẬP NHẬT GIÁ (MỚI THÊM)
    update_status("📉 Bước 0: Cập nhật dữ liệu giá mới nhất...", 10)
    try:
        fetch_recent_data_online()
    except Exception as e:
        print(f"⚠️ Lỗi cập nhật giá: {e}")

    # BƯỚC 1: CRAWL TIN TỨC
    update_status("📰 Bước 1: Thu thập dữ liệu tin tức & mạng xã hội...", 30)
    try:
        main_posts_crawling(target_date_obj)
        main_news_crawling(target_date_obj)
    except Exception as e:
        print(f"⚠️ Lỗi Crawling: {e}")
    
    # BƯỚC 2: TÓM TẮT & XÂY GRAPH
    update_status("🧠 Bước 2: Tóm tắt và xây dựng đồ thị tri thức...", 50)

    
    daily_graph = build_daily_knowledge_graph_batch(target_date_str + " 00:00:00")
    
    # BƯỚC 3: TÍCH HỢP NEO4J
    update_status("💾 Bước 3: Lưu trữ vào Neo4j...", 70)
    if daily_graph.number_of_nodes() > 0:
        save_graph(daily_graph)
    
    # BƯỚC 4: TRR MEMORY
    update_status("🔍 Bước 4: Kích hoạt TRR Memory & Attention...", 80)
    trr = TRRMemoryAttention()
    G_full = trr.fetch_historical_graph(target_date_str)
    G_attention = trr.apply_attention_mechanism(G_full, PORTFOLIO_STOCKS)
    graph_context = trr.format_graph_for_llm(G_attention)
    trr.close()
    
    if not graph_context:
        graph_context = "Không có sự kiện quan trọng nào."
    
    # BƯỚC 5: DỰ ĐOÁN (LLM)
    update_status("🔮 Bước 5: AI đang suy luận & dự đoán...", 90)
    predictor = StockPredictor()
    results = {}
    
    for ticker in PORTFOLIO_STOCKS:
        prediction = predictor.predict(ticker=ticker, graph_context=graph_context, target_date=target_date_str)
        results[ticker] = prediction
        print(f"Prediction for {ticker}:\n{prediction}\n{'-'*30}\n")
        
        # time.sleep(1) # Giảm delay để nhanh hơn

    # BƯỚC 6: LƯU KẾT QUẢ
    save_predictions_to_db(results, target_date_str)

    update_status(f"✅ Hoàn thành phân tích ngày {target_date_str}!", 100)
    return results

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    run_full_pipeline(today)