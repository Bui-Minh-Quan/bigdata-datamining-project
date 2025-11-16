import os
import time
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

import requests
import pandas as pd
from dateutil import parser
from data_preprocessing import preprocess_news_df

# =========================
# CONFIG
# =========================
API_URL = "https://api.fireant.vn/posts"
AUTH_BEARER = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoyMDYyMTA0NDA5LCJuYmYiOjE3NjIxMDQ0MDksImNsaWVudF9pZCI6ImZpcmVhbnQud2ViIiwic2NvcGUiOlsib3BlbmlkIiwicHJvZmlsZSIsInJvbGVzIiwiZW1haWwiLCJhY2NvdW50cy1yZWFkIiwiYWNjb3VudHMtd3JpdGUiLCJvcmRlcnMtcmVhZCIsIm9yZGVycy13cml0ZSIsImNvbXBhbmllcy1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImZpbmFuY2UtcmVhZCIsInBvc3RzLXdyaXRlIiwicG9zdHMtcmVhZCIsInN5bWJvbHMtcmVhZCIsInVzZXItZGF0YS1yZWFkIiwidXNlci1kYXRhLXdyaXRlIiwidXNlcnMtcmVhZCIsInNlYXJjaCIsImFjYWRlbXktcmVhZCIsImFjYWRlbXktd3JpdGUiLCJibG9nLXJlYWQiLCJpbnZlc3RvcGVkaWEtcmVhZCJdLCJzdWIiOiIyMWU5OTg0NC03ODljLTQxMGMtYWU4ZC00MmE0N2MwOGM4NDUiLCJhdXRoX3RpbWUiOjE3NjIxMDQ0MDksImlkcCI6Ikdvb2dsZSIsIm5hbWUiOiJidWltaW5ocXVhbmR6MjAwNUBnbWFpbC5jb20iLCJzZWN1cml0eV9zdGFtcCI6IjQ5ODExNzUxLWE5YWMtNDliMy1hNzBmLWFiNWVlMzkyZTcwZCIsImp0aSI6IjVhNDEzYTFhY2U1YjYyZGMyMWUwNjc0NWQ3MzFkMjQyIiwiYW1yIjpbImV4dGVybmFsIl19.cVnpsLaA50c-xTXx-5xJRr0TldZrH3Owu1z7i6qyq6eHR7aFIHyXa4ooMU12E6tg8fQYZR01kU2OBvgc_wQTqzQaFLX6d3eZmB8rA4b8RD1s2DzIoo3f1BlK_gDQRcE_iLRTfmDHwRZk4GvPLGKPkm24wAYd0gAwB9RcrtA4wz77w9IOHSVpqgrDKX_ww-U947cYeiGLBbgaSz7IIM0j30f_ZFPDUOGnVrGnS4bQZCyuqsZiMizUr5A3ivJuz8mXMlxMIaJbS_LwMTwsBY2FBn-hPBXrVozjYZxh22C9PfJ6U0kjV_UO4nUeKWMen3kbRdZW7lzR3TohDQlU9DXDXw"  # Replace with a default token if needed



LIMIT = 1000
OFFSET_STEP = LIMIT
MAX_RETRY = 5
REQUEST_TIMEOUT = 20
MIN_DELAY = 0.3
MAX_DELAY = 1.0

OUTPUT_DIR = "crawling/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
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
            logger.warning(f"API {url} returned status {r.status_code}, retry {retry+1}/{max_retry}")
        except requests.RequestException as e:
            logger.warning(f"Request exception: {e} (retry {retry+1}/{max_retry})")

        time.sleep(backoff + random.uniform(0, 0.5))
        backoff *= 2
        retry += 1

    logger.error(f"Max retries reached for {url} -> returning None")
    return None

# =========================
# Crawl logic
# =========================
def crawl_news() -> List[Dict]:
    """Crawl posts from NOW -> 0:00:00 of yesterday."""
    now = datetime.now(timezone(timedelta(hours=7)))
    day_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = day_start.replace(tzinfo=timezone(timedelta(hours=7)))

    logger.info(f"Start crawling news from {now.isoformat()} to {day_start.isoformat()}")

    offset = 0
    collected_posts: List[Dict] = []

    while True:
        params = {"type": 1, "offset": offset, "limit": LIMIT}
        batch = api_get(API_URL, params)
        if not batch:
            logger.info("No more posts returned -> stop crawling")
            break

        batch_has_target = False
        for post in batch:
            try:
                post_date = parser.isoparse(post.get("date"))
            except Exception:
                continue

            if day_start <= post_date <= now:
                # Fetch post detail to get full content
                post_id = post.get("postID")
                if not post_id:
                    continue
                detail = api_get(f"{API_URL}/{post_id}", {})
                if not detail:
                    continue

                collected_posts.append(detail)
                batch_has_target = True

        if not batch_has_target:
            logger.info("No posts in this batch match target date -> stop crawling")
            break

        offset += OFFSET_STEP
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    logger.info(f"Collected {len(collected_posts)} posts")
    return collected_posts

# =========================
# Post-processing
# =========================
def process_post(post: Dict) -> Dict:
    """Keep only necessary fields."""
    return {
        "postID": post.get("postID"),
        "date": post.get("date"),
        "title": post.get("title"),
        "description": post.get("description"),
        "originalContent": post.get("content"),
        "sentiment": post.get("sentiment"),
        "totalLikes": post.get("totalLikes"),
        "totalReplies": post.get("totalReplies"),
        "totalShares": post.get("totalShares"),
    }

def save_to_csv(posts: List[Dict]):
    if not posts:
        logger.warning("No posts to save")
        return
    df = pd.DataFrame([process_post(p) for p in posts])
    
    preprocess_news_df(df)
    
    filename = os.path.join(OUTPUT_DIR, f"news_{datetime.now():%Y-%m-%d}.csv")
    df.to_csv(filename, index=False, encoding="utf-8")
    logger.info(f"Saved {len(df)} posts to {filename}")

# =========================
# Main
# =========================
def main():
    raw_posts = crawl_news()
    save_to_csv(raw_posts)

if __name__ == "__main__":
    main()
