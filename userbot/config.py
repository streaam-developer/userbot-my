import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram API Credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Target Channel ID where videos will be forwarded
target_channel_id = os.getenv('TARGET_CHANNEL_ID')
if not target_channel_id:
    raise ValueError("TARGET_CHANNEL_ID must be set in environment variables")
TARGET_CHANNEL_ID = int(target_channel_id)

# Bot username to monitor (configurable via env)
TARGET_BOT_USERNAME = os.getenv('TARGET_BOT_USERNAME', '@boltarhegabot')

# Session name
SESSION_NAME = "userbot_session"