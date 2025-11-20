import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from pymongo import UpdateOne 
from database.db import get_database
import logging 
import os
import sys

from database.db import get_database
db = get_database()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


processed_news_collection = db['news']
summarized_news_collection = db['summarized_news']

# Place Holder for summarization function
def summarize_text(text):
    if not text:
        return ""
    
    return text

def run_summarization(batch_size=100):
    # Get postID of documents that are already summarized
    summarized_ids = set(
        summarized_news_collection.distinct("postID")
    )
    
    logger.info(f"{len(summarized_ids)} posts already summarized.")
    
    # get all processed news that are not yet summarized
    query = {} if not summarized_ids else {"postID": {"$nin": list(summarized_ids)}}
    cursor = processed_news_collection.find(query, batch_size=batch_size)
    
    operations = []
    count = 0
    for news in cursor:
        postID = news.get("postID")
        stockCodes = news.get("taggedSymbols", [])
        title = news.get("title", "")
        description = news.get("description", "")
        
        date = news.get('date', None)
        
        
        doc = {
            "postID": postID,
            "stockCodes": stockCodes,
            "title": title,
            "description": description,
            "date": date
        }
        
        operations.append(UpdateOne({"postID": postID}, {"$set": doc}, upsert=True))
        count += 1 
        
        # commit in batches
        if len(operations) >= batch_size:
            summarized_news_collection.bulk_write(operations)
            logger.info(f"Summarized and saved {len(operations)} posts.")
            operations = []
            
        # Commit any remaining operations
    if operations:
        summarized_news_collection.bulk_write(operations)
        logger.info(f"Summarized and saved {len(operations)} posts.")
    
    logger.info(f"Summarization completed. Total posts summarized: {count}")

if __name__ == "__main__":
    run_summarization(batch_size=100)