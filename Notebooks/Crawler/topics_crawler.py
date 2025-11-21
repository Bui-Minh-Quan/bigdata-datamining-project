import requests
import csv
import os
import time
import random
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import logging

# Configuration
BASE = "https://f319.com/"
INPUT_FILE = "topics.csv"
OUTPUT_DIR = "data"
PROGRESS_FILE = "progress.txt"
MAX_WORKERS = 20  # Number of concurrent threads
BATCH_SIZE = 100000  # Number of posts per output CSV
RETRY_ATTEMPTS = 3  # Number of retries for failed requests
USER_AGENTS = [
    # Windows / Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.129 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",

    # macOS / Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",

    # Linux / Firefox
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",

    # Android Chrome
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.174 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G996B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Mobile Safari/537.36",

    # iPhone Safari
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.7 Mobile/15E148 Safari/604.1",

    # Edge (Chromium)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.123 Safari/537.36 Edg/123.0.2420.97",

    # Linux / Chrome
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.76 Safari/537.36"
]


# Set up logging
logging.basicConfig(
    filename="scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Thread-safe lock for batch_posts and progress file
batch_lock = Lock()
progress_lock = Lock()

# Helper functions
def load_completed_urls():
    """Load set of completed topic URLs from progress.txt."""
    completed_urls = set()
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                completed_urls = set(line.strip() for line in f if line.strip())
        except Exception as e:
            logging.error(f"Failed to load progress file: {e}")
    return completed_urls

def save_completed_urls(completed_urls):
    """Append a set of completed topic URLs to progress.txt."""
    with progress_lock:
        try:
            with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
                for url in completed_urls:
                    f.write(f"{url}\n")
        except Exception as e:
            logging.error(f"Failed to save completed URLs to progress file: {e}")

def get_total_pages(soup):
    """Get number of pages in a topic thread."""
    try:
        nav = soup.find("span", class_="pageNavHeader")
        if not nav or "/" not in nav.text:
            return 1
        total_pages = nav.text.split("/")[-1].strip()
        return int(total_pages) if total_pages.isdigit() else 1
    except Exception as e:
        logging.error(f"Error parsing total pages: {e}")
        return 1

def crawl_topic(url, title):
    """Crawl all posts in a topic."""
    posts = []
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    for attempt in range(RETRY_ATTEMPTS):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            total_pages = get_total_pages(soup)
            
            for page in range(1, total_pages + 1):
                page_url = f"{url}page-{page}" if page > 1 else url
                try:
                    r = requests.get(page_url, headers=headers, timeout=10)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")
                    
                    for msg in soup.find_all("div", class_="messageInfo"):
                        # Extract date/time from <a class="datePermalink"> (unchanged as requested)
                        time_tag = msg.find('a', class_='datePermalink')
                        date = time_tag.text.strip() if time_tag else ""
                        
                        content_block = msg.find("blockquote", class_="messageText")
                        content = content_block.get_text("\n", strip=True) if content_block else ""
                        
                        posts.append({
                            "topic_title": title,
                            "topic_url": url,
                            "page": page,
                            "post_time": date,
                            "content": content
                        })
                    
                    # Delay between pages
                    time.sleep(random.uniform(0.1, 0.3))
                
                except requests.RequestException as e:
                    logging.error(f"Failed to fetch page {page} of {url}: {e}")
                    continue
                
            return posts
        
        except requests.RequestException as e:
            logging.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(random.uniform(1, 3))
            continue
    
    logging.error(f"Failed to crawl {url} after {RETRY_ATTEMPTS} attempts")
    return posts

def load_topics():
    """Load topics from CSV."""
    if not os.path.exists(INPUT_FILE):
        logging.error(f"Input file {INPUT_FILE} not found")
        raise FileNotFoundError(f"Input file {INPUT_FILE} not found")
    
    topics = []
    try:
        with open(INPUT_FILE, newline='', encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if 'url' not in reader.fieldnames or 'title' not in reader.fieldnames:
                raise ValueError("Input CSV must have 'url' and 'title' columns")
            for row in reader:
                topics.append((row['url'], row['title']))
        return topics
    except Exception as e:
        logging.error(f"Failed to load topics from {INPUT_FILE}: {e}")
        raise

def write_batch(posts, path, completed_urls_temp):
    """Write a list of posts to CSV and save completed URLs."""
    try:
        with open(path, 'w', newline="", encoding="utf-8-sig", errors="replace") as f:
            writer = csv.DictWriter(f, fieldnames=['topic_title', 'topic_url', 'page', "post_time", "content"])
            writer.writeheader()
            writer.writerows(posts)
        # Save completed URLs after successful batch write
        save_completed_urls(completed_urls_temp)
    except Exception as e:
        logging.error(f"Failed to write batch to {path}: {e}")

def crawl_all_topics():
    """Crawl all topics, skipping completed ones."""
    try:
        topics = load_topics()
    except Exception as e:
        print(f"Error loading topics: {e}")
        return
    
    # Load completed URLs
    completed_urls = load_completed_urls()
    topics_to_crawl = [(url, title) for url, title in topics if url not in completed_urls]
    
    print(f"Total {len(topics_to_crawl)} topics to crawl (out of {len(topics)}).")
    
    batch_num = len(completed_urls) // BATCH_SIZE
    batch_posts = []
    completed_urls_temp = set()  # Temporary set for completed URLs
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(crawl_topic, url, title): url
                   for url, title in topics_to_crawl}
        
        for future in as_completed(futures):
            url = futures[future]
            try:
                result = future.result()
                with batch_lock:
                    if result:
                        batch_posts.extend(result)
                        completed_urls_temp.add(url)  # Add URL to temporary set
                    
                    # Save batch when limit reached
                    if len(batch_posts) >= BATCH_SIZE:
                        batch_num += 1
                        output_path = os.path.join(OUTPUT_DIR, f"posts_{batch_num:04d}.csv")
                        write_batch(batch_posts, output_path, completed_urls_temp)
                        batch_posts = []
                        completed_urls_temp = set()  # Reset temporary set
                        print(f"[SAVED] Batch {batch_num} after crawling {url}")
            except Exception as e:
                logging.error(f"Error processing topic {url}: {e}")
        
        # Save final batch
        with batch_lock:
            if batch_posts:
                batch_num += 1
                output_path = os.path.join(OUTPUT_DIR, f"posts_{batch_num:04d}.csv")
                write_batch(batch_posts, output_path, completed_urls_temp)
                print(f"[SAVED] Final batch {batch_num}")

if __name__ == "__main__":
    crawl_all_topics()