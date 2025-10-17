import logging
import os

from dotenv import load_dotenv

# MongoDB setup with error handling
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    print("Warning: pymongo not available. Running without MongoDB support.")
    MONGODB_AVAILABLE = False
    MongoClient = None

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Telegram API Credentials
API_ID = os.getenv('API_ID', "904789")
if not API_ID:
    raise ValueError("API_ID must be set in environment variables")
API_HASH = os.getenv('API_HASH', "2262ef67ced426b9eea57867b11666a1")
if not API_HASH:
    raise ValueError("API_HASH must be set in environment variables")
BOT_TOKEN = os.getenv('BOT_TOKEN', "7932992967:AAEEImgpNBjIs0bpgjCbAuQ6J8at9ynB_8I")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set in environment variables")


# Target Channel ID where videos will be forwarded
target_channel_id = os.getenv('TARGET_CHANNEL_ID', "-1002818242381")
if not target_channel_id:
    raise ValueError("TARGET_CHANNEL_ID must be set in environment variables")
TARGET_CHANNEL_ID = int(target_channel_id)

# Post Channel ID where original posts will be forwarded
post_channel_id = os.getenv('POST_CHANNEL_ID', "-1002818242381")
if not post_channel_id:
    raise ValueError("POST_CHANNEL_ID must be set in environment variables")
POST_CHANNEL_ID = int(post_channel_id)

# Bot usernames to monitor (configurable via env, comma-separated)
TARGET_BOT_USERNAMES = os.getenv(
    'TARGET_BOT_USERNAMES',
    '@Dairy_share2bot,@quality_filesbot,@File_extractorbot,@Flipkart_filebot,@Kitkat_sharebot,@Unfiltered_filebot,@Desiiihub_bot,@Sanzzyyyyyfree_bot,@Instaidsbot,@Arararararararobot,@UwUlinkbot,@Oneetouch_bot,@File_senderrbot,@Niggerndra_bot,@Happystreettsbot,@Juicerequestbot,@Earningtipssbot,@Monkepostingbot,@Premiumposterrbot,@MarleGbot,@Lmaoxdfilebot,@arigatooooooobot,@Onisannnnnbot,@Amazon_sharebot'
).split(',')

TARGET_BOT_USERNAME = TARGET_BOT_USERNAMES[0]  # Keep for backward compatibility

# Session name
SESSION_NAME = "userbot_session"

# For link generation
FILE_STORE_CHANNEL = [TARGET_CHANNEL_ID]

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb+srv://sonukumarkrbbu60:lfkTvljnt25ehTt9@cluster0.2wrbftx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'userbot_db')

# MongoDB Client
try:
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client[DATABASE_NAME]
    # Test connection
    mongo_client.admin.command('ping')
    logger.info("MongoDB connected successfully")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise
