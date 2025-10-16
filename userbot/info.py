"""
Bot information and configuration constants
"""
import os

from config import TARGET_BOT_USERNAMES

# Bot usernames for link generation (same as target bots)
BOT_USERNAMES = TARGET_BOT_USERNAMES

# File store channel - use the target channel as file store
FILE_STORE_CHANNEL = [os.getenv('TARGET_CHANNEL_ID', "-1003128443058")]