import os
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

import requests
import pandas as pd
from dateutil import parser

# Import hàm preprocessing từ file cùng thư mục
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
    # Token mặc định (Nên cập nhật thường xuyên)
    AUTH_BEARER = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDYyMTA0NDA5LCJuYmYiOjE3NjIxMDQ0MDksImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiIyMWU5OTg0NC03ODljLTQxMGMtYWU4ZC00MmE0N2MwOGM4NDUiLCJhdXRoX3RpbWUiOjE3NjIxMDQ0MDksImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJidWltaW5ocXVhbmR6MjAwNUBnbWFpbC5jb20iLCJzZWN1cml0eV9zdGFtcCI6IjQ5ODExNzUxLWE5YWMtNDliMy1hNzBmLWFiNWVlMzkyZTcwZCIsImp0aSI6IjVhNDEzYTFhY2U1YjYyZGMyMWUwNjc0NWQ3MzFkMjQyIiwiYW1yIjpbImV4dGVybmFsIl19.cVnpsLaA50c-xTXx-5xJRr0TldZrH3Owu1z7i6qyq6eHR7aFIHyXa4ooMU12E6tg8fQYZR01kU2OBvgc_wQTqzQaFLX6d3eZmB8rA4b8RD1s2DzIoo3f1BlK_gDQRcE_iLRTfmDHwRZk4GvPLGKPkm24wAYd0gAwB9RcrtA4wz77w9IOHSVpqgrDKX_ww-U947cYeiGLBbgaSz7IIM0j30f_ZFPDUOGnVrGnS4bQZCyuqsZiMizUr5A3ivJuz8mXMlxMIaJbS_LwMTwsBY2FBn-hPBXrVozjYZxh22C9PfJ6U0kjV_UO4nUeKWMen3kbRdZW7lzR3TohDQlU9DXDXw"

# Cấu hình Crawl
TARGET_DAY_DEFAULT = (datetime.now() - timedelta(days=1)).date()
LIMIT = 500          # Giảm limit xuống 500 vì news nặng hơn posts
PROBE_LIMIT = 1
OFFSET_STEP = LIMIT
MAX_RETRY = 5
REQUEST_TIMEOUT = 20
MIN_DELAY = 0.5
MAX_DELAY = 1.5

# Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("news_crawler")

# =========================
# Helpers: API calls
# =========================
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {AUTH_BEARER}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

def api_get(url: str, params: Dict[str, object], max_retry: int = MAX_RETRY) -> Optional[List[Dict]]:
    """Gọi API có retry"""
    retry = 0
    backoff = 1.0
    while retry < max_retry:
        try:
            r = requests.get(url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"API {url} status={r.status_code}, retry={retry+1}/{max_retry}")
        except requests.RequestException as e:
            logger.warning(f"Request exception: {e} (retry {retry+1}/{max_retry})")

        time.sleep(backoff + random.uniform(0, 0.5))
        backoff *= 2
        retry += 1

    logger.error(f"Max retries reached for {url}")
    return None

# =========================
# Core crawl logic (SMART PROBE)
# =========================
def crawl_news(target_day) -> List[Dict]:
    """
    Crawl News (type=1) cho một ngày cụ thể.
    Sử dụng logic thăm dò để nhảy cóc qua các ngày mới hơn.
    """
    # 1. Chuẩn hóa ngày tháng
    if isinstance(target_day, str):
        try:
            target_day = datetime.strptime(target_day, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"❌ Định dạng ngày không hợp lệ: {target_day}")
            return []
            
    if target_day is None:
        target_day = TARGET_DAY_DEFAULT
        
    # 2. Xác định khung thời gian (Time Window UTC)
    day_start = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    
    logger.info(f"🚀 Bắt đầu crawl News cho ngày: {target_day} (Window UTC: {day_start} -> {day_end})")
    
    offset = 0
    collected_posts: List[Dict] = []
    
    while True:
        # --- Bước A: Thăm dò (Probe) ---
        # type=1 là News (Tin tức)
        probe_params = {"type": 1, "offset": offset, "limit": PROBE_LIMIT}
        probe = api_get(API_URL, probe_params)
        
        if probe is None: break
        if len(probe) == 0:
            logger.info("Probe rỗng -> Hết dữ liệu -> Dừng.")
            break
            
        try:
            probe_date = parser.isoparse(probe[0].get("date"))
        except:
            logger.warning("Lỗi parse date bài probe -> Bỏ qua batch.")
            offset += OFFSET_STEP
            continue

        # --- Bước B: Quyết định ---
        
        # 1. Nếu tin còn mới quá (Tương lai) -> Nhảy cóc
        if probe_date >= day_end:
            # logger.info(f"Đang ở vùng tin mới ({probe_date}) -> Nhảy offset...")
            offset += OFFSET_STEP
            time.sleep(random.uniform(MIN_DELAY, 0.5))
            continue
            
        # 2. Nếu tin đã cũ quá (Quá khứ) -> Dừng
        if probe_date < day_start:
            logger.info(f"Đã chạm vùng tin cũ ({probe_date}) -> Dừng crawl.")
            break
            
        # 3. Nếu đúng vùng cần lấy -> Tải chi tiết
        # logger.info(f"🎯 Tìm thấy tin mục tiêu. Tải batch tại offset {offset}...")
        
        batch_params = {"type": 1, "offset": offset, "limit": LIMIT}
        batch = api_get(API_URL, batch_params)
        
        if not batch: break
        
        items_in_batch = 0
        for p in batch:
            try:
                post_date = parser.isoparse(p.get("date"))
            except:
                continue
                
            # Lọc tin trong batch (vì batch có thể chứa lẫn lộn)
            if post_date >= day_end: continue
            if post_date < day_start: 
                # Vì đã sort giảm dần, gặp tin cũ là dừng luôn cả hàm
                logger.info(f"Gặp tin cũ trong batch ({post_date}) -> Hoàn tất.")
                return collected_posts

            # --- QUAN TRỌNG: Lấy chi tiết bài báo ---
            # Tin tức thường bị cắt ngắn ở danh sách, cần gọi API detail
            post_id = p.get("postID")
            if post_id:
                detail = api_get(f"{API_URL}/{post_id}", {})
                if detail:
                    collected_posts.append(detail)
                    items_in_batch += 1
                    
        logger.info(f"   + Đã lấy {items_in_batch} tin chi tiết từ batch (Offset: {offset})")
        
        offset += OFFSET_STEP
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    logger.info(f"✅ Hoàn thành crawl News. Tổng số tin: {len(collected_posts)}")
    return collected_posts

# =========================
# Processing & Saving
# =========================
def process_post(post: Dict) -> Optional[Dict]:
    """Làm sạch dữ liệu tin tức"""
    try:
        postID = post.get("postID")
        if not postID: return None
        
        # Clean Date
        date_raw = post.get("date")
        try:
            date_str = parser.isoparse(date_raw).isoformat() if date_raw else None
        except:
            date_str = date_raw
            
        # Clean Symbols
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
            "originalContent": post.get("content"), # Content tin tức
            "sentiment": post.get("sentiment"),
            "taggedSymbols": cleaned_symbols,
            "totalLikes": post.get("totalLikes", 0),
            "totalReplies": post.get("totalReplies", 0),
            "totalShares": post.get("totalShares", 0),
        }
    except Exception:
        return None

def save_news_to_db(processed: List[Dict]):
    """Lưu vào DB thông qua preprocess_news_df"""
    if not processed: return
    
    df = pd.DataFrame(processed)
    # Hàm này trong data_preprocessing.py đã có logic lưu vào collection 'news' và 'processed_news'
    preprocess_news_df(df)

# =========================
# Main Entry Point
# =========================
def main_news_crawling(target_day=None):
    """Hàm gọi chính"""
    raw_posts = crawl_news(target_day)
    
    if not raw_posts:
        logger.warning("Không tìm thấy tin tức nào.")
        return

    logger.info("Đang xử lý dữ liệu tin tức...")
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
        logger.info(f"Lưu {len(processed_list)} tin tức vào Database...")
        save_news_to_db(processed_list)
    else:
        logger.warning("Không có tin tức hợp lệ sau khi xử lý.")

if __name__ == "__main__":
    main_news_crawling()