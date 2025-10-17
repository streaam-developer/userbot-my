"""
MongoDB database manager for link tracking and video processing
"""
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, mongodb_uri, database_name):
        """Initialize database connection"""
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client[database_name]
        self.processed_links = self.db.processed_links
        self._setup_indexes()

    def _setup_indexes(self):
        """Setup required indexes"""
        # Create indexes in background
        self.processed_links.create_index("original_link", unique=True, background=True)
        self.processed_links.create_index("processed_at", background=True)

    async def is_link_processed(self, original_link):
        """Check if a link has already been processed"""
        doc = await self.processed_links.find_one({"original_link": original_link})
        return doc is not None

    async def add_processed_link(self, original_link, new_link, video_info=None):
        """Add a processed link to database"""
        try:
            doc = {
                "original_link": original_link,
                "new_link": new_link,
                "video_info": video_info or {},
                "processed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await self.processed_links.insert_one(doc)
            logger.info(f"Added processed link to database: {original_link} -> {new_link}")
            return True
        except DuplicateKeyError:
            logger.warning(f"Link already exists in database: {original_link}")
            return False
        except Exception as e:
            logger.error(f"Error adding link to database: {str(e)}")
            return False

    async def update_processed_link(self, original_link, new_link):
        """Update an existing processed link"""
        try:
            result = await self.processed_links.update_one(
                {"original_link": original_link},
                {
                    "$set": {
                        "new_link": new_link,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated processed link in database: {original_link} -> {new_link}")
            return success
        except Exception as e:
            logger.error(f"Error updating link in database: {str(e)}")
            return False

    async def get_processed_link(self, original_link):
        """Get processed link information"""
        try:
            doc = await self.processed_links.find_one({"original_link": original_link})
            return doc
        except Exception as e:
            logger.error(f"Error fetching link from database: {str(e)}")
            return None

    async def get_processed_link_by_video_id(self, video_file_id):
        """Get processed link information by video file ID"""
        try:
            doc = await self.processed_links.find_one({"video_info.file_id": video_file_id})
            return doc
        except Exception as e:
            logger.error(f"Error fetching link by video ID from database: {str(e)}")
            return None

    async def close(self):
        """Close database connection"""
        self.client.close()