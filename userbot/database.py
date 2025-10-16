
import pymongo
from config import MONGO_DB_NAME, MONGO_URI

client = pymongo.MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
processed_urls_collection = db["processed_urls"]

def is_url_processed(url):
    """Check if a URL has already been processed."""
    return processed_urls_collection.find_one({"url": url}) is not None

def add_processed_url(url):
    """Add a new processed URL to the database."""
    processed_urls_collection.insert_one({"url": url})
