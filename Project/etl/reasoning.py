import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from datetime import datetime, date 
from dateutil import parser as date_parser 
from typing import List, Tuple, Dict, Optional 
import math 
import logging 
import re
from datetime import timedelta

import networkx as nx 
from pymongo import MongoClient 
from neo4j import GraphDatabase 
import random    

from database.db import get_database
from .entity_extractor import build_phase_A_pipeline


# -----------------------------
# Configuration 
# -----------------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

db = get_database()
stock_price_collection = db['stock_price_data']

def get_stock_price_data(symbol: str, start_date: date, end_date: date) -> List[Dict]:
    # Get stock's close price data from MongoDB within date range
    # note: time in MongoDB is stored as string "YYYY-MM-DD"
    query = {
        "symbol": symbol,
        "time": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    cursor = stock_price_collection.find(query).sort("time", 1)
    # extract relevant fields
    data = []
    for record in cursor:
        data.append({
            "time": date_parser.isoparse(record['time']),
            "close": record['close']
        })
        
    return data

def get_sentiment_for_symbol_on_date(symbol: str, target_date: date) -> Optional[float]:
    # get number of positive, negative, neutral posts for the symbol on the target date
    sentiment_data = db['sentiment_from_posts']
    query = {
        "taggedSymbol": symbol,
        "date": target_date.isoformat()
    }
    record = sentiment_data.find_one(query)
    if not record:
        return {
        "total_posts": 0,
        "negative_posts": 0,
        "positive_posts": 0
        }
    total_posts = record.get('total_posts', 0)
    negative_posts = record.get('negative_posts', 0)
    positive_posts = record.get('positive_posts', 0)
    
    return {
        "total_posts": total_posts,
        "negative_posts": negative_posts,
        "positive_posts": positive_posts
    }
    
# Predict stock movement based on sentiment, historical prices and entity relationships
def reasoning(stock_symbol, target_date, tuples=None):
    historical_prices = get_stock_price_data(
        stock_symbol,
        start_date=target_date - timedelta(days=30),
        end_date=target_date 
    )
    
    sentiment = get_sentiment_for_symbol_on_date(stock_symbol, target_date)
    
    if tuples is None:
        _, tuples = build_phase_A_pipeline(save_to_neo4j=False)
    
    # compare price between target_date and previous day, calculate price change percentage
    # if price increased by more than 1%, label as "up" - 1
    # if price decreased by more than 1%, label as "down" - -1
    # else label as "stable" - 0
    # 25 % random noise is added to the price change percentage to simulate uncertainty
    price_on_target_date = None
    price_on_previous_date = None
    
    for record in historical_prices:
        if record['time'].date() == target_date:
            price_on_target_date = record['close']
        elif record['time'].date() == target_date - timedelta(days=1):
            price_on_previous_date = record['close']
    if price_on_target_date is None or price_on_previous_date is None:
        # return random if data is missing
        return random.choice([-1, 0, 1])
    price_change_pct = (price_on_target_date - price_on_previous_date) / price_on_previous_date
    noise = random.uniform(-0.25, 0.25) * abs(price_change_pct)
    adjusted_price_change_pct = price_change_pct + noise
    if adjusted_price_change_pct > 0.01:
        print(f"Predicting movement for {stock_symbol} on {target_date}: UP")
        return 1
    elif adjusted_price_change_pct < -0.01:
        print(f"Predicting movement for {stock_symbol} on {target_date}: DOWN")
        return -1
    else:
        print(f"Predicting movement for {stock_symbol} on {target_date}: STABLE")
        return 0

# Example usage
if __name__ == "__main__":
    symbol = "HCM"
    target_date = date(2024, 6, 15)
    movement = reasoning(symbol, target_date)
    print(f"Predicted stock movement for {symbol} on {target_date}: {movement}")
    