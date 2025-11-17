from bs4 import BeautifulSoup
import html 
import pandas as pd 
import sys, os
from bs4 import MarkupResemblesLocatorWarning
import warnings
import ast
import numpy as np

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from database.db import get_database
db = get_database()


def parse_tagged_symbols(x):
    if isinstance(x, list):
        return x
    elif isinstance(x, np.ndarray):
        return x.tolist()
    elif isinstance(x, str):
        try:
            return ast.literal_eval(x)
        except:
            return []
    elif pd.isna(x):
        return []
    else:
        return []


# Clean HTML content from text
def clean_html(text):
    if pd.isna(text):
        return text
    # Remove HTML tags
    warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text()
    # Unescape HTML entities
    cleaned_text = html.unescape(cleaned_text)
    return cleaned_text


    
# Combine multiple fields into a single text field
def combine_content(row):
    # combine title, description, originalContent into on text field 
    """  
    format:
    Title: {title}
    Description: {description}
    Content: {originalContent}
    """
    content_parts = []
    if pd.notna(row['title']):
        content_parts.append(f"Title: {row['title']}")
    if pd.notna(row['description']):
        content_parts.append(f"Description: {row['description']}")
    if pd.notna(row['originalContent']):
        content_parts.append(f"Content: {row['originalContent']}")
        
    return "\n".join(content_parts)

# Sentiment extraction from posts dataframe for symbols
def extract_sentiment(df: pd.DataFrame):
    df = df.copy()
    # Drop columns originalContent, postID 
    df = df.drop(columns=['originalContent', 'postID'], errors='ignore')
    
    # Explode taggedSymbols column
    df['taggedSymbols'] = df['taggedSymbols'].apply(parse_tagged_symbols)
    df = df.explode('taggedSymbols')
    df = df.dropna(subset=['taggedSymbols'])
    
    # Handle date column: convert to datetime, then to date string YYYY-MM-DD
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date.astype(str)
    
    # Group by date and taggedSymbols
    sentiment_summary = df.groupby(['date', 'taggedSymbols']).agg(
        positive_posts=('sentiment', lambda x: (x == 1).sum()),
        negative_posts=('sentiment', lambda x: (x == -1).sum()),
        neutral_posts=('sentiment', lambda x: (x == 0).sum()),
        total_posts=('sentiment', 'count')
    ).reset_index()
    
 

    
    return sentiment_summary



# -----------------------------
# Preprocessing functions
# -----------------------------
def preprocess_posts_df(df: pd.DataFrame):
    df = df.copy()
    df['originalContent'] = df['originalContent'].apply(clean_html)
    
    # -----------------------------
    # Lưu posts vào MongoDB
    # -----------------------------
    posts_col = db["posts"]
    # tạo index unique cho postID
    posts_col.create_index("postID", unique=True)
    
    for _, row in df.iterrows():
        doc = {
            "postID": row["postID"],
            "date": str(pd.to_datetime(row["date"])),
            "originalContent": row.get("originalContent"),
            "sentiment": row.get("sentiment"),
            "taggedSymbols": row.get("taggedSymbols", [])
        }
        try:
            posts_col.update_one({"postID": doc["postID"]}, {"$set": doc}, upsert=True)
        except Exception as e:
            print(f"Error saving postID={doc['postID']}: {e}")
    
    print(f"Saved {len(df)} posts to MongoDB 'posts' collection")
    # -----------------------------
    # Tạo sentiment summary
    # -----------------------------
    sentiment_summary = extract_sentiment(df)
    sentiment_col = db["sentiment_from_posts"]
    sentiment_col.create_index([("date", 1), ("taggedSymbols", 1)], unique=True)
    
    for _, row in sentiment_summary.iterrows():
        doc = row.to_dict()
        try:
            sentiment_col.update_one(
                {"date": doc["date"], "taggedSymbols": doc["taggedSymbols"]},
                {"$set": doc},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving sentiment {doc}: {e}")
    
    print(f"Saved sentiment summary for {len(sentiment_summary)} (date, symbol) pairs to MongoDB 'sentiment_from_posts' collection")
    


# Clean and preprocess news dataframe
def preprocess_news_df(df: pd.DataFrame):
    df = df.copy()
    df['originalContent'] = df['originalContent'].apply(clean_html)
    df['content'] = df.apply(combine_content, axis=1)
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date.astype(str)
    
    processed_df = df[['postID' ,'date', 'content']]
    
    # -----------------------------
    # Lưu news vào MongoDB
    # -----------------------------
    news_col = db["news"]
    news_col.create_index("postID", unique=True)
    processed_news_col = db["processed_news"]
    processed_news_col.create_index("date", unique=False)
    
    for _, row in df.iterrows():
        doc = {
            "postID": row["postID"],
            "date": str(pd.to_datetime(row["date"])),
            "title": row.get("title"),
            "description": row.get("description"),
            "originalContent": row.get("originalContent"),
            "sentiment": row.get("sentiment"),
            "totalLikes": row.get("totalLikes", 0),
            "totalReplies": row.get("totalReplies", 0),
            "totalShares": row.get("totalShares", 0)
        }
        try:
            news_col.update_one({"postID": doc["postID"]}, {"$set": doc}, upsert=True)
        except Exception as e:
            print(f"Error saving news postID={doc['postID']}: {e}")
    
    print(f"Saved {len(df)} news to MongoDB 'news' collection")
    
    
    # lưu processed_news
    for _, row in processed_df.iterrows():
        doc = row.to_dict()
        try:
            processed_news_col.update_one(
                {"postID": doc['postID'],"date": doc["date"], "content": doc["content"]},
                {"$set": doc},
                upsert=True
            )
        except Exception as e:
            print(f"Error saving processed_news {doc}: {e}")
            
    print(f"Saved {len(processed_df)} processed news to MongoDB 'processed_news' collection")
    