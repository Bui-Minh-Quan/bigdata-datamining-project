import os
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

import requests
import pandas as pd
from dateutil import parser

# Import hàm preprocessing
try:
    from .data_preprocessing import preprocess_news_df
except ImportError:
    from data_preprocessing import preprocess_news_df

# =========================
# CONFIG
# =========================
API_URL = "https://api.fireant.vn/posts"
AUTH_BEARER = os.getenv("FIREANT_BEARER")

if not AUTH_BEARER:
    # Token mặc định
    AUTH_BEARER = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDYyMTA0NDA5LCJuYmYiOjE3NjIxMDQ0MDksImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiIyMWU5OTg0NC03ODljLTQxMGMtYWU4ZC00MmE0N2MwOGM4NDUiLCJhdXRoX3RpbWUiOjE3NjIxMDQ0MDksImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJidWltaW5ocXVhbmR6MjAwNUBnbWFpbC5jb20iLCJzZWN1cml0eV9zdGFtcCI6IjQ5ODExNzUxLWE5YWMtNDliMy1hNzBmLWFiNWVlMzkyZTcwZCIsImp0aSI6IjVhNDEzYTFhY2U1YjYyZGMyMWUwNjc0NWQ3MzFkMjQyIiwiYW1yIjpbImV4dGVybmFsIl19.cVnpsLaA50c-xTXx-5xJRr0TldZrH3Owu1z7i6qyq6eHR7aFIHyXa4ooMU12E6tg8fQYZR01kU2OBvgc_wQTqzQaFLX6d3eZmB8rA4b8RD1s2DzIoo3f1BlK_gDQRcE_iLRTfmDHwRZk4GvPLGKPkm24wAYd0gAwB9RcrtA4wz77w9IOHSVpqgrDKX_ww-U947cYeiGLBbgaSz7IIM0j30f_ZFPDUOGnVrGnS4bQZCyuqsZiMizUr5A3ivJuz8mXMlxMIaJbS_LwMTwsBY2FBn-hPBXrVozjYZxh22C9PfJ6U0kjV_UO4nUeKWMen3kbRdZW7lzR3TohDQlU9DXDXw"

# Cấu hình Crawl
LIMIT = 500          
PROBE_LIMIT = 1
OFFSET_STEP = LIMIT
MAX_RETRY = 5
REQUEST_TIMEOUT = 20
MIN_DELAY = 0.5
MAX_DELAY = 1.5

# Cấu hình Logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("news_crawler")

# =========================
# Helpers
# =========================
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {AUTH_BEARER}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

def api_get(url: str, params: Dict[str, object], max_retry: int = MAX_RETRY) -> Optional[List[Dict]]:
    retry = 0
    backoff = 1.0
    while retry < max_retry:
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"API {url} status={r.status_code}, retry={retry+1}")
        except Exception as e:
            logger.warning(f"Request exception: {e}")
        time.sleep(backoff + random.uniform(0, 0.5))
        backoff *= 2
        retry += 1
    return None

# =========================
# CORE LOGIC (ĐÃ SỬA THEO YÊU CẦU)
# =========================
def crawl_news(target_day=None) -> List[Dict]:
    """
    Crawl tin tức từ thời điểm hiện tại lùi về quá khứ.
    Điểm dừng: 00:00:00 của 'target_day' (hoặc hôm qua nếu không truyền).
    Logic: Quét từ Offset 0 (Mới nhất) -> Cũ dần.
    """
    # 1. Xác định ngày mốc (Cutoff Date)
    if target_day is None:
        # Mặc định là 00:00:00 hôm qua
        target_day = (datetime.now() - timedelta(days=1)).date()
    elif isinstance(target_day, str):
        target_day = datetime.strptime(target_day, "%Y-%m-%d").date()

    # 2. Chuyển đổi sang thời gian có múi giờ (UTC+7 cho Việt Nam)
    # Mẹo: Fireant dùng UTC. 00:00:00 VN = 17:00:00 hôm trước (UTC)
    # Để an toàn và đơn giản, ta dùng timestamp so sánh
    
    # Mốc dừng: 00:00:00 của target_day (Giờ Việt Nam)
    # => Đổi sang UTC để so sánh với dữ liệu API
    vn_tz = timezone(timedelta(hours=7))
    cutoff_time_vn = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=vn_tz)
    cutoff_time_utc = cutoff_time_vn.astimezone(timezone.utc)

    logger.info(f"🚀 Bắt đầu crawl News từ Hiện tại lùi về {cutoff_time_vn} (VN) / {cutoff_time_utc} (UTC)")
    
    offset = 0
    collected_posts: List[Dict] = []
    
    while True:
        # --- Bước A: Lấy Batch tin tức ---
        batch_params = {"type": 1, "offset": offset, "limit": LIMIT}
        batch = api_get(API_URL, batch_params)
        
        if not batch: 
            logger.info("Không lấy được batch hoặc hết dữ liệu -> Dừng.")
            break
        
        items_in_batch = 0
        stop_signal = False
        
        for p in batch:
            try:
                post_date = parser.isoparse(p.get("date"))
            except:
                continue
            
            # --- QUAN TRỌNG: Điều kiện dừng ---
            # Nếu gặp bài viết CŨ HƠN mốc cutoff -> Dừng toàn bộ việc crawl
            if post_date < cutoff_time_utc:
                logger.info(f"🛑 Gặp tin cũ ({post_date}) < Cutoff ({cutoff_time_utc}) -> Dừng.")
                stop_signal = True
                break # Thoát vòng for

            # Nếu bài viết >= Cutoff -> Lấy chi tiết
            post_id = p.get("postID")
            if post_id:
                # Gọi API Detail để lấy nội dung full
                detail = api_get(f"{API_URL}/{post_id}", {})
                if detail:
                    collected_posts.append(detail)
                    items_in_batch += 1
        
        logger.info(f"   + Batch {offset}: Lấy được {items_in_batch} tin mới.")
        
        # Nếu gặp tín hiệu dừng trong batch vừa rồi -> Thoát vòng while
        if stop_signal:
            break
            
        # Nếu batch trả về ít hơn limit (tức là trang cuối) -> Cũng dừng
        if len(batch) < LIMIT:
            logger.info("Đã đến trang cuối cùng của API -> Dừng.")
            break

        # Tăng offset để lấy trang tiếp theo (lùi xa hơn về quá khứ)
        offset += OFFSET_STEP
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    logger.info(f"✅ Hoàn thành. Tổng số tin thu thập: {len(collected_posts)}")
    return collected_posts

# =========================
# Processing & Saving
# =========================
def process_post(post: Dict) -> Optional[Dict]:
    """Làm sạch dữ liệu"""
    try:
        postID = post.get("postID")
        if not postID: return None
        
        date_raw = post.get("date")
        try:
            date_str = parser.isoparse(date_raw).isoformat() if date_raw else None
        except:
            date_str = date_raw
            
        tagged_symbols = post.get("taggedSymbols")
        if not isinstance(tagged_symbols, list):
            cleaned_symbols = []
        else:
            cleaned_symbols = [sym['symbol'] for sym in tagged_symbols if isinstance(sym, dict) and 'symbol' in sym]
            
        return {
            "postID": postID,
            "date": date_str,
            "title": post.get("title"),
            "description": post.get("description"),
            "originalContent": post.get("content"),
            "sentiment": post.get("sentiment"),
            "taggedSymbols": cleaned_symbols,
            "totalLikes": post.get("totalLikes", 0),
            "totalReplies": post.get("totalReplies", 0),
            "totalShares": post.get("totalShares", 0),
        }
    except Exception:
        return None

def save_news_to_db(processed: List[Dict]):
    if not processed: return
    df = pd.DataFrame(processed)
    preprocess_news_df(df)

# =========================
# Main Entry Point
# =========================
def main_news_crawling(target_day=None):
    raw_posts = crawl_news(target_day)
    
    if not raw_posts:
        logger.warning("Không tìm thấy tin tức nào trong khoảng thời gian yêu cầu.")
        return

    logger.info(f"Đang xử lý và lưu {len(raw_posts)} tin tức...")
    processed_list = []
    seen_ids = set()
    
    for p in raw_posts:
        out = process_post(p)
        if out:
            pid = out.get("postID")
            if pid not in seen_ids:
                seen_ids.add(pid)
                processed_list.append(out)
            
    if processed_list:
        save_news_to_db(processed_list)
        logger.info("Lưu DB thành công.")

if __name__ == "__main__":
    # Test chạy
    target_date_str = (datetime.now() - timedelta(days=600)).strftime("%Y-%m-%d")
    main_news_crawling(target_date_str)