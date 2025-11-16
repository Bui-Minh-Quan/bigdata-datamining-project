from pymongo import MongoClient

def get_mongo_client():
    # Local MongoDB mặc định chạy ở port 27017
    mongo_url = "mongodb://localhost:27017"
    
    client = MongoClient(mongo_url)
    return client

def get_database(db_name="bigdata_trr"):
    client = get_mongo_client()
    db = client[db_name]
    return db
