import os
import time
import json
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from data_preprocessing import preprocess_posts_df


import requests
import pandas as pd
from dateutil import parser

# ===========================
# CONFIG
# ===========================
API_URL = "https://api.fireant.vn/posts"
AUTH_BEARER = os.getenv("FIREANT_BEARER")

if not AUTH_BEARER:
    AUTH_BEARER = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDYyMTA0NDA5LCJuYmYiOjE3NjIxMDQ0MDksImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiIyMWU5OTg0NC03ODljLTQxMGMtYWU4ZC00MmE0N2MwOGM4NDUiLCJhdXRoX3RpbWUiOjE3NjIxMDQ0MDksImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJidWltaW5ocXVhbmR6MjAwNUBnbWFpbC5jb20iLCJzZWN1cml0eV9zdGFtcCI6IjQ5ODExNzUxLWE5YWMtNDliMy1hNzBmLWFiNWVlMzkyZTcwZCIsImp0aSI6IjVhNDEzYTFhY2U1YjYyZGMyMWUwNjc0NWQ3MzFkMjQyIiwiYW1yIjpbImV4dGVybmFsIl19.cVnpsLaA50c-xTXx-5xJRr0TldZrH3Owu1z7i6qyq6eHR7aFIHyXa4ooMU12E6tg8fQYZR01kU2OBvgc_wQTqzQaFLX6d3eZmB8rA4b8RD1s2DzIoo3f1BlK_gDQRcE_iLRTfmDHwRZk4GvPLGKPkm24wAYd0gAwB9RcrtA4wz77w9IOHSVpqgrDKX_ww-U947cYeiGLBbgaSz7IIM0j30f_ZFPDUOGnVrGnS4bQZCyuqsZiMizUr5A3ivJuz8mXMlxMIaJbS_LwMTwsBY2FBn-hPBXrVozjYZxh22C9PfJ6U0kjV_UO4nUeKWMen3kbRdZW7lzR3TohDQlU9DXDXw"  # Replace with a default token if needed


# crawl target
TARGET_DAY = (datetime.now() - timedelta(days=1)).date()  # yesterday

# crawling configuration
LIMIT = 1000 # number of posts to fetch per request
PROBE_LIMIT = 1  # number of posts to probe to decide whether to continue crawling
OFFSET_STEP = LIMIT 
MAX_RETRY = 5 
REQUEST_TIMEOUT = 20  # seconds
MIN_DELAY = 0.3  # seconds
MAX_DELAY = 1.2 # seconds

# FILE OUTPUT
OUTPU_DIR = "crawling/output"
os.makedirs(OUTPU_DIR, exist_ok=True)

# logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("posts_crawler")

# =========================
# Helpers: API calls with retry/backoff
# =========================

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {AUTH_BEARER}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    
def api_get(params: Dict[str, object], max_retry: int = MAX_RETRY) -> Optional[List[Dict]]:
    # call api with retries. Returns parsed JSON list on succes, None on fatal failure 
    retry = 0
    backoff = 1.0
    while retry < max_retry:
        try:
            r = requests.get(API_URL, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
            status = r.status_code
            if status == 200:
                try:
                    return r.json()
                except Exception as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    return None 
            
            # 401/403/404/429 are handled as warnings and retried a few times
            logger.warning(f"API {API_URL} status={status}, retry={retry+1}/{max_retry}")
        
        except requests.RequestException as e:
            logger.warning(f"Request exception: {e} (retry {retry+1}/{max_retry})")
            
        
        # backoff + small jitter
        sleep_t = backoff + random.uniform(0, 0.5)
        time.sleep(sleep_t)
        backoff *= 2
        retry += 1
        
        logger.error("Max retry reached -> returning None")
        return None
    
# =========================
# Post processing
# =========================

def process_post(raw: dict) -> Optional[Dict]:
    try:
        postID = raw.get("postID")
        date_raw = raw.get("date")
        
        if not date_raw:
            return None 
        
        try: 
            dt = parser.isoparse(date_raw)
            date_str = dt.isoformat()
            
        except Exception:
            date_str = date_raw 
        
        # tagged symbols
        tagged = raw.get("taggedSymbols") or []
        cleaned_symbols = []
        for s in tagged:
            try:
                cleaned_symbols.append(s.get("symbol"))
            
            except:
                continue 
        
        out = {
            "postID": postID,
            "date": date_str,
            "originalContent": raw.get("originalContent"),
            "sentiment": raw.get("sentiment"),
            "taggedSymbols": cleaned_symbols
        }
        
        return out 
    
    except Exception as e:
        logger.debug(f"process_post exception: {e}")
        return None
    
# =========================
# Core crawl logic
# =========================
def crawl_posts(target_day: datetime.date = TARGET_DAY) -> List[Dict]:
    # crawl posts in the previous day
    day_end = datetime.now(timezone(timedelta(hours=7))) 
    day_start = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone(timedelta(hours=7)))
    
    logger.info(f"Start crawling posts for {target_day} (from {day_start} to {day_end})")
    
    offset = 0
    collected_raw: List[Dict] = []
    
    while True:
        # Probe: check post at 'offset'
        probe_params = {"type": 0, "offset": offset, "limit": PROBE_LIMIT}
        probe = api_get(probe_params)
        
        if probe is None: 
            logger.warning("Probe returned None -> stopping crawl")
            break 
        
        if len(probe) == 0:
            logger.info("Probe returned empty -> no more data at this offset -> stopping")
            break
        
        probe_post = probe[0]
        try:
            probe_date = parser.isoparse(probe_post.get("date"))
        except Exception:
            logger.warning("Probe post has no parsable date -> stopping to be safe")
            break
        
        logger.info(f"Probe at offset {offset} -> post date {probe_date.isoformat()}")
        
        # if the probe post is older than day_start 
        if probe_date < day_start:
            logger.info("Probe post older than day_start -> reached old zone -> stopping crawl")
            break
        
        # if probe post is newer or equal to day_end, keep crawling
        if probe_date >= day_end:
            logger.info("Probe post newer than target day_end -> increment offset to skip newer posts")
            offset += OFFSET_STEP
            # small delay
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            continue
        
        # Otherwise, the batch likely contains posts within the target day: fetch full batch
        batch_params = {"type": 0, "offset": offset, "limit": LIMIT}
        batch = api_get(batch_params)
        
        if batch is None:
            logger.warning("Batch fetch returned None -> stop crawl")
            break
        
        if len(batch) == 0:
            logger.info("Batch empty -> stopping")
            break
            
        logger.info(f"Fetched batch offset={offset} size={len(batch)}")
        
        # Add batch to collected and optionally stop when oldest < day_start
        for p in batch:
            try:
                dt = parser.isoparse(p.get("date"))
            except Exception:
                continue

            if day_start <= dt < day_end:
                collected_raw.append(p)
                batch_has_target_day = True
        if not batch_has_target_day:
            logger.info("No posts in this batch match target day -> stop crawling")
            break
        

        
        # Next offset
        offset += OFFSET_STEP
        
        # polite delay
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        
    logger.info(f"Crawling finished. Collected raw posts: {len(collected_raw)}")
    return collected_raw

# =========================
# Save function (CSV per day, append if exists)
# =========================
def save_posts_csv(processed: List[Dict], target_day: datetime.date = TARGET_DAY) -> str:
    if not processed:
        logger.warning("No processed posts to save.")
        return ""
    
    df = pd.DataFrame(processed)
    
    preprocess_posts_df(df)
    
    filename = os.path.join(OUTPU_DIR, f"posts_{target_day:%Y-%m-%d}.csv")
    try:
        df.to_csv(filename, index=False, encoding="utf-8")
        logger.info(f"Saved {len(df)} rows to new {filename}")
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        
    
    return filename



# =========================
# Main
# =========================
def main(target_day: Optional[datetime.date] = None):
    if target_day is None: 
        target_day = TARGET_DAY 
    
    raw = crawl_posts(target_day)
    logger.info("Processing posts...")
    processed = []
    seen_ids = set()

    for r in raw:
        out = process_post(r)
        if not out:
            continue 
        pid = out.get("postID")
        if pid in seen_ids:
            continue 
        seen_ids.add(pid)
        processed.append(out)
    
    if processed:
        save_posts_csv(processed, target_day)
    else: 
        logger.warning("No posts processed for saving.")

if __name__ == "__main__":
    main()