from pymongo import MongoClient, ASCENDING

def init_collections():
    client = MongoClient("mongodb://localhost:27017")
    db = client["bigdata_trr"]

    # ----- POSTS -----
    posts = db["posts"]
    posts.create_index([("postID", ASCENDING)], unique=True)
    
    # ----- NEWS -----
    news = db["news"]
    news.create_index([("postID", ASCENDING)], unique=True)

    # ----- PROCESSED NEWS -----
    processed_news = db["processed_news"]
    processed_news.create_index([("postID", ASCENDING)], unique=True)

    # ----- SENTIMENT FROM POSTS -----
    sentiment = db["sentiment_from_posts"]
    sentiment.delete_many({"$or": [{"symbol": None}, {"date": None}]})
  

    # ----- SUMMARIZED NEWS -----
    summarized = db["summarized_news"]
    summarized.create_index([("postID", ASCENDING)], unique=True)

    print("All collections initialized successfully with indexes.")

if __name__ == "__main__":
    init_collections()
