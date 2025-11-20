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
    from .data_preprocessing import preprocess_posts_df
except ImportError:
    from data_preprocessing import preprocess_posts_df

# ===========================
# CONFIG
# ===========================
API_URL = "https://api.fireant.vn/posts"
# Lấy Bearer Token từ biến môi trường hoặc dùng token mặc định
AUTH_BEARER = os.getenv("FIREANT_BEARER")
if not AUTH_BEARER:
    AUTH_BEARER = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDYyMTA0NDA5LCJuYmYiOjE3NjIxMDQ0MDksImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiIyMWU5OTg0NC03ODljLTQxMGMtYWU4ZC00MmE0N2MwOGM4NDUiLCJhdXRoX3RpbWUiOjE3NjIxMDQ0MDksImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJidWltaW5ocXVhbmR6MjAwNUBnbWFpbC5jb20iLCJzZWN1cml0eV9zdGFtcCI6IjQ5ODExNzUxLWE5YWMtNDliMy1hNzBmLWFiNWVlMzkyZTcwZCIsImp0aSI6IjVhNDEzYTFhY2U1YjYyZGMyMWUwNjc0NWQ3MzFkMjQyIiwiYW1yIjpbImV4dGVybmFsIl19.cVnpsLaA50c-xTXx-5xJRr0TldZrH3Owu1z7i6qyq6eHR7aFIHyXa4ooMU12E6tg8fQYZR01kU2OBvgc_wQTqzQaFLX6d3eZmB8rA4b8RD1s2DzIoo3f1BlK_gDQRcE_iLRTfmDHwRZk4GvPLGKPkm24wAYd0gAwB9RcrtA4wz77w9IOHSVpqgrDKX_ww-U947cYeiGLBbgaSz7IIM0j30f_ZFPDUOGnVrGnS4bQZCyuqsZiMizUr5A3ivJuz8mXMlxMIaJbS_LwMTwsBY2FBn-hPBXrVozjYZxh22C9PfJ6U0kjV_UO4nUeKWMen3kbRdZW7lzR3TohDQlU9DXDXw"

# Cấu hình Crawl
TARGET_DAY_DEFAULT = (datetime.now() - timedelta(days=1)).date()  # Mặc định là hôm qua
LIMIT = 1000         # Số lượng bài viết mỗi lần request
PROBE_LIMIT = 1      # Số lượng bài viết thăm dò để kiểm tra ngày
OFFSET_STEP = LIMIT  # Bước nhảy offset
MAX_RETRY = 5        # Số lần thử lại khi lỗi mạng
REQUEST_TIMEOUT = 20 # Giây
MIN_DELAY = 0.3      # Giây
MAX_DELAY = 1.2      # Giây

# Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("posts_crawler")

# =========================
# Helpers: API calls
# =========================
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {AUTH_BEARER}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    
def api_get(params: Dict[str, object], max_retry: int = MAX_RETRY) -> Optional[List[Dict]]:
    """Gọi API có cơ chế thử lại (Retry) và chờ (Backoff)"""
    retry = 0
    backoff = 1.0
    while retry < max_retry:
        try:
            r = requests.get(API_URL, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            
            logger.warning(f"API {API_URL} status={r.status_code}, retry={retry+1}/{max_retry}")
        except requests.RequestException as e:
            logger.warning(f"Request exception: {e} (retry {retry+1}/{max_retry})")
            
        time.sleep(backoff + random.uniform(0, 0.5))
        backoff *= 2
        retry += 1
        
    logger.error("Max retry reached -> returning None")
    return None

# =========================
# Core crawl logic (REWRITTEN)
# =========================
def crawl_posts(target_day) -> List[Dict]:
    """
    Hàm crawl posts chính.
    Input: target_day (str "YYYY-MM-DD" hoặc datetime.date object)
    Output: List[Dict] (Danh sách các bài raw posts)
    """
    
    # 1. Chuẩn hóa ngày tháng (SỬA LỖI TYPE ERROR TẠI ĐÂY)
    if isinstance(target_day, str):
        try:
            target_day = datetime.strptime(target_day, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"❌ Định dạng ngày không hợp lệ: {target_day}. Dùng YYYY-MM-DD.")
            return []
            
    if target_day is None:
        target_day = TARGET_DAY_DEFAULT
    
    # 2. Xác định khung thời gian (Time Window) theo UTC
    # Fireant dùng giờ UTC, ta lấy từ 00:00:00 ngày target đến 00:00:00 ngày hôm sau
    day_start = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    
    logger.info(f"🚀 Bắt đầu crawl Posts cho ngày: {target_day} (Window UTC: {day_start} -> {day_end})")
    
    offset = 0
    collected_raw: List[Dict] = []
    
    while True:
        # --- Bước A: Thăm dò (Probe) ---
        # Kiểm tra nhanh 1 bài tại vị trí offset hiện tại xem đang ở ngày nào
        probe_params = {"type": 0, "offset": offset, "limit": PROBE_LIMIT}
        probe = api_get(probe_params)
        
        if probe is None: # Lỗi mạng fatal
            break 
        
        if len(probe) == 0:
            logger.info("Probe trả về rỗng -> Đã hết dữ liệu trên server -> Dừng.")
            break
        
        # Lấy ngày của bài viết thăm dò
        try:
            probe_date = parser.isoparse(probe[0].get("date"))
        except Exception:
            logger.warning("Không đọc được ngày của bài probe -> Bỏ qua batch này.")
            offset += OFFSET_STEP
            continue
            
        # logger.info(f"Probe tại offset {offset} -> Ngày bài viết: {probe_date}")

        # --- Bước B: Quyết định dựa trên ngày thăm dò ---
        
        # Trường hợp 1: Bài thăm dò nằm trong TƯƠNG LAI so với ngày cần lấy
        # (Ví dụ: Cần lấy ngày 19, probe đang thấy ngày 20) -> Nhảy cóc
        if probe_date >= day_end:
            # logger.info(f"Đang ở vùng dữ liệu mới ({probe_date}) -> Nhảy offset để tìm ngày {target_day}...")
            offset += OFFSET_STEP
            time.sleep(random.uniform(MIN_DELAY, 0.5)) # Delay ngắn để lướt nhanh
            continue
            
        # Trường hợp 2: Bài thăm dò nằm trong QUÁ KHỨ so với ngày cần lấy
        # (Ví dụ: Cần lấy ngày 19, probe thấy ngày 18) -> Đã đi quá xa -> Dừng
        if probe_date < day_start:
            logger.info(f"Đã chạm vùng dữ liệu cũ ({probe_date}) -> Dừng crawl.")
            break
            
        # Trường hợp 3: Bài thăm dò nằm TRONG ngày cần lấy (hoặc gần đó) -> Tải thật
        # logger.info(f"🎯 Tìm thấy dữ liệu mục tiêu. Tải batch tại offset {offset}...")
        
        batch_params = {"type": 0, "offset": offset, "limit": LIMIT}
        batch = api_get(batch_params)
        
        if not batch:
            break
            
        # Lọc chi tiết từng bài trong batch
        items_in_batch = 0
        for p in batch:
            try:
                dt = parser.isoparse(p.get("date"))
            except:
                continue

            # Nếu bài viết > day_end (vẫn còn mới quá, do batch có thể trộn lẫn): Bỏ qua
            if dt >= day_end:
                continue
                
            # Nếu bài viết < day_start (đã sang ngày hôm trước): Dừng toàn bộ
            if dt < day_start:
                logger.info(f"Gặp bài viết cũ ({dt}) trong batch -> Hoàn tất.")
                # Lưu ý: Return luôn tại đây vì Fireant sắp xếp theo thời gian giảm dần
                return collected_raw 

            # Nếu đúng ngày
            collected_raw.append(p)
            items_in_batch += 1
            
        logger.info(f"   + Đã lấy {items_in_batch} bài từ batch (Offset: {offset})")
        
        # Tăng offset để lấy batch tiếp theo
        offset += OFFSET_STEP
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        
    logger.info(f"✅ Hoàn thành crawl Posts. Tổng số bài raw: {len(collected_raw)}")
    return collected_raw

# =========================
# Post Processing & Saving
# =========================
def process_post(raw: dict) -> Optional[Dict]:
    """Làm sạch một bài post raw"""
    try:
        postID = raw.get("postID")
        if not postID: return None
        
        # Clean Date
        date_raw = raw.get("date")
        try: 
            date_str = parser.isoparse(date_raw).isoformat() if date_raw else None
        except:
            date_str = date_raw
            
        # Clean Symbols
        tagged = raw.get("taggedSymbols") or []
        cleaned_symbols = [s.get("symbol") for s in tagged if isinstance(s, dict) and "symbol" in s]
        
        return {
            "postID": postID,
            "date": date_str,
            "originalContent": raw.get("originalContent"),
            "sentiment": raw.get("sentiment"),
            "taggedSymbols": cleaned_symbols
        }
    except Exception:
        return None

def save_posts_to_db(processed: List[Dict]):
    """Chuyển list dict thành DataFrame và gọi hàm preprocess để lưu DB"""
    if not processed:
        return
    
    df = pd.DataFrame(processed)
    # Gọi hàm từ data_preprocessing.py (đã có logic lưu MongoDB)
    preprocess_posts_df(df)

# =========================
# Main Entry Point
# =========================
def main_posts_crawling(target_day=None):
    """Hàm chính để gọi từ bên ngoài pipeline"""
    # 1. Crawl
    raw_posts = crawl_posts(target_day)
    
    if not raw_posts:
        logger.warning("Không tìm thấy bài viết nào.")
        return

    # 2. Process
    logger.info("Đang xử lý dữ liệu thô...")
    processed_posts = []
    seen_ids = set()

    for r in raw_posts:
        out = process_post(r)
        if out:
            pid = out.get("postID")
            if pid not in seen_ids:
                seen_ids.add(pid)
                processed_posts.append(out)
    
    # 3. Save
    if processed_posts:
        logger.info(f"Lưu {len(processed_posts)} bài viết vào Database...")
        save_posts_to_db(processed_posts)
    else:
        logger.warning("Không có bài viết hợp lệ sau khi xử lý.")

if __name__ == "__main__":
    main_posts_crawling()