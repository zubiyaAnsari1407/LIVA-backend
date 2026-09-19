import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent / ".env")

client = MongoClient(
    os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017"),
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)

db = client[os.getenv("MONGODB_DB", "liva")]