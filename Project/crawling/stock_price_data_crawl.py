import os 
import sys

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

import pandas 
from database.db import get_database
db = get_database()

def crawl_stock_price_data():
    # take data from .csv files in crawling/stock_price_data/.csv
    data_dir = os.path.join(ROOT_DIR, "crawling", "stock_price_data")
    all_data = []
    
    # extract symbols from filenames
    symbols = []
    for filename in os.listdir(data_dir):
        if filename.endswith(".csv"):
            symbol = filename[:-4]  # remove .csv
            symbols.append(symbol)
            
            filepath = os.path.join(data_dir, filename)
            df = pandas.read_csv(filepath)
            df['symbol'] = symbol
            all_data.append(df)
    
    if all_data:
        combined_df = pandas.concat(all_data, ignore_index=True)
        return combined_df
    else:
        return pandas.DataFrame()  # empty dataframe

if __name__ == "__main__":
    df = crawl_stock_price_data()
    print(f"Crawled stock price data with {len(df)} rows.")
    print(df.head())
    
    # Save to mongoDB
    stock_price_collection = db['stock_price_data']
    records = df.to_dict(orient='records')
    if records:
        stock_price_collection.delete_many({})  # clear existing data
        stock_price_collection.insert_many(records)
        print(f"Inserted {len(records)} records into MongoDB collection 'stock_price_data'.")
    else:
        print("No records to insert into MongoDB.")

