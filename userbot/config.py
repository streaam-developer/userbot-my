import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram API Credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Target Channel ID where videos will be forwarded
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))

# Bot username to monitor
TARGET_BOT_USERNAME = "@boltarhegabot"

# Session name
SESSION_NAME = "userbot_session"