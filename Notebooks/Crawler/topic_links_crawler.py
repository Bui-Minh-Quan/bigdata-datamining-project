import requests
from bs4 import BeautifulSoup
import csv
import os
import time
import random

BASE = "https://f319.com/"
FORUM_URL = "https://f319.com/forums/thi-truong-chung-khoan.3/page-{}"
OUTPUT_FILE = "topics.csv"
COMPLETED_LOG = "completed_pages.log"
FAILED_LOG = "failed_pages.log"

# --- Configuration ---
RETRY_ATTEMPTS = 3
SLEEP_BETWEEN_REQUESTS = (0.2, 0.5)
SLEEP_BETWEEN_RETRIES = (2, 5)

USER_AGENTS = [
    # Windows / Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.126 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.174 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
    # macOS / Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Linux / Firefox
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.76 Safari/537.36 Edg/125.0.2535.51",
    # Android / iOS
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.174 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

def load_logged_pages(filename):
    """Return a set of page numbers recorded in a log file."""
    if not os.path.exists(filename):
        return set()
    with open(filename, "r", encoding="utf-8") as f:
        return {int(line.strip()) for line in f if line.strip().isdigit()}

def append_log(filename, page_number):
    """Append a page number to a log file."""
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{page_number}\n")

def get_topics(start_page=1, end_page=5500):
    # Resume info
    completed_pages = load_logged_pages(COMPLETED_LOG)
    print(f"{len(completed_pages)} pages already completed.")
    print(f"Will crawl from page {start_page} to {end_page}.")

    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["url", "title"])

        for i in range(start_page, end_page + 1):
            if i in completed_pages:
                print(f"[SKIP] Page {i} already done.")
                continue

            success = False
            for attempt in range(RETRY_ATTEMPTS):
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                try:
                    r = requests.get(FORUM_URL.format(i), headers=headers, timeout=10)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")

                    topics = []
                    for h3 in soup.select("h3.title a"):
                        link = BASE + h3.get("href", "").strip()
                        title = h3.get_text(strip=True)
                        topics.append([link, title])

                    writer.writerows(topics)
                    print(f"[OK] Page {i}: {len(topics)} topics saved.")
                    append_log(COMPLETED_LOG, i)
                    success = True
                    break
                except Exception as e:
                    print(f"[WARN] Page {i} attempt {attempt+1}/{RETRY_ATTEMPTS} failed: {e}")
                    time.sleep(random.uniform(*SLEEP_BETWEEN_RETRIES))

            if not success:
                print(f"[FAIL] Page {i} after {RETRY_ATTEMPTS} attempts.")
                append_log(FAILED_LOG, i)

            time.sleep(random.uniform(*SLEEP_BETWEEN_REQUESTS))
    
    print("Successfully crawled all topics✅")

if __name__ == "__main__":
    get_topics(1, 1)

