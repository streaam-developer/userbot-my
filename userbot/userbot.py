import asyncio
import logging
import re
from datetime import datetime

from bot_handlers import BotHandlers
from channel_manager import ChannelManager
from config import (
    API_HASH,
    API_ID,
    SESSION_NAME,
    TARGET_BOT_USERNAME,
    TARGET_BOT_USERNAMES,
    db,
    MONGODB_AVAILABLE,
)
from telethon import TelegramClient, events
from telethon.errors import (
    ApiIdInvalidError,
    AuthKeyInvalidError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerIdInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    TimeoutError,
    UserBannedInChannelError,
)
from video_processor import VideoProcessor

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='userbot.log'
)
# Add console handler for detailed terminal output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)

logger = logging.getLogger(__name__)

# Initialize client with proper type checking
if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH must be set in environment variables")
client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

class UserBot:
    def __init__(self):
        # MongoDB collections (only if available)
        if MONGODB_AVAILABLE:
            self.links_collection = db['processed_links']
            self.processing_collection = db['processing_links']
            self.videos_collection = db['processed_videos']
        else:
            self.links_collection = None
            self.processing_collection = None
            self.videos_collection = None

        # Initialize helper classes
        self.bot_handlers = BotHandlers(self)
        self.video_processor = VideoProcessor(client)
        self.channel_manager = ChannelManager(client)

    async def join_channel(self, channel_link):
        """Join a channel using the channel manager"""
        return await self.channel_manager.join_channel(channel_link)

    async def forward_video(self, message):
        """Forward video using the video processor"""
        return await self.video_processor.forward_video(message)

    async def download_and_reupload_video(self, message):
        """Download and re-upload video using the video processor"""
        return await self.video_processor.download_and_reupload_video(message)

    async def process_bot_link(self, bot_link):
        """Process bot link and extract videos, return access link if generated"""
        logger.info(f"Starting to process bot link: {bot_link}")
        try:
            # Check if link is already processed in MongoDB (if available)
            if MONGODB_AVAILABLE and self.links_collection is not None:
                existing_link = self.links_collection.find_one({"original_link": bot_link, "status": "processed"})
                if existing_link:
                    logger.info(f"Link {bot_link} has already been successfully processed, skipping")
                    return existing_link.get("access_links", [])

                # Check if link is currently being processed
                processing_doc = self.processing_collection.find_one({"link": bot_link})
                if processing_doc:
                    logger.info(f"Link {bot_link} is already being processed, skipping")
                    return None

                # Mark link as processing
                self.processing_collection.insert_one({
                    "link": bot_link,
                    "started_at": datetime.utcnow()
                })
                logger.info(f"Marked {bot_link} as processing in database")
            additional_bot_links = []
            videos_found = False  # Flag to stop processing once videos are found
            access_links = []  # To collect access links generated
            try:
                # Extract bot username from the link
                bot_username_match = re.search(r't\.me/([a-zA-Z0-9_]+bot)', bot_link)
                if not bot_username_match:
                    logger.warning(f"Could not extract bot username from link: {bot_link}")
                    # Fallback to target bot username if not found in link
                    bot_username = TARGET_BOT_USERNAME
                else:
                    bot_username = bot_username_match.group(1)
#
                # Extract the start parameter or any bot command from the link
                if 'start=' in bot_link:
                    start_param = bot_link.split('start=')[-1]
                    bot_command = f"/start {start_param}"
                    logger.info(f"Extracted start parameter: {start_param}, using command: {bot_command}")
                else:
                    bot_command = bot_link
                    logger.info(f"Using link as command: {bot_command}")

                logger.info(f"Starting conversation with @{bot_username}")
                async with client.conversation(bot_username) as conv:
                    logger.info(f"Sending command to bot: {bot_command}")
                    await conv.send_message(bot_command)
                    logger.info("Waiting for bot response...")
                    response = await conv.get_response(timeout=30)
                    logger.info(f"Received response from bot: {response.text[:200]}...")

                    # Handle channel join requirement
                    if "join" in response.text.lower() or "channel" in response.text.lower():
                        logger.info("Bot requires channel join, extracting channel links...")
                        channel_links = re.findall(r'https://t\.me/[^\s\n]+', response.text)
                        username_links = re.findall(r'@([a-zA-Z0-9_]+)', response.text)
                        for username in username_links:
                            if username not in ['join', 'channel', 'the', 'to', 'and', 'or']:
                                channel_links.append(f"https://t.me/{username}")

                        logger.info(f"Found {len(channel_links)} channel links to join: {channel_links}")
                        joined_channels = []
                        for channel_link in channel_links:
                            if bot_username.lower() in channel_link.lower():
                                logger.info(f"Skipping bot link: {channel_link}")
                                continue
                            logger.info(f"Attempting to join channel: {channel_link}")
                            success = await self.join_channel(channel_link)
                            if success:
                                logger.info(f"Successfully joined channel: {channel_link}")
                                joined_channels.append(channel_link)
                            else:
                                logger.error(f"Failed to join channel: {channel_link}")
                            await asyncio.sleep(5)  # Increased delay to avoid floodwait

                        if joined_channels:
                            logger.info("Re-sending command after joining channels...")
                            await conv.send_message(bot_command)
                            response = await conv.get_response(timeout=30)
                            logger.info(f"Received response after joining: {response.text[:200]}...")
                        else:
                            logger.warning("No channels were successfully joined, continuing with current response")

                    # Check for inline buttons and click them to get more content
                    if hasattr(response, 'buttons') and response.buttons:
                        logger.info(f"Found {len(response.buttons)} button rows, clicking buttons to get more content...")
                        for row_idx, button_row in enumerate(response.buttons):
                            for btn_idx, button in enumerate(button_row):
                                if hasattr(button, 'url') and button.url:
                                    logger.info(f"Processing button URL: {button.url}")
                                    if 't.me/' in button.url and ('joinchat' in button.url or '/+' in button.url or '@' in button.url):
                                        logger.info(f"Button contains channel link, attempting to join: {button.url}")
                                        success = await self.join_channel(button.url)
                                        if success:
                                            logger.info(f"Successfully joined channel from button: {button.url}")
                                        else:
                                            logger.error(f"Failed to join channel from button: {button.url}")
                                    else:
                                        # Collect bot links for later processing instead of skipping
                                        if 't.me/' in button.url and 'bot' in button.url:
                                            logger.info(f"Found nested bot link in button, collecting for later: {button.url}")
                                            additional_bot_links.append(button.url)
                                        else:
                                            logger.warning(f"Skipping non-bot link in button: {button.url}")
                                    await asyncio.sleep(5)  # Increased delay to avoid floodwait
                                elif hasattr(button, 'data'):
                                    logger.info(f"Clicking inline button with data: {button.data}")
                                    try:
                                        await response.click(button.data)
                                        new_response = await conv.get_response(timeout=30)
                                        logger.info(f"Received response after button click: {new_response.text[:200]}...")

                                        # Check if video is forwardable, if not, download and re-upload
                                        if hasattr(new_response, 'video') and new_response.video:
                                            video_file_id = (new_response.video.id, new_response.video.size)
                                            # Check if video is already processed in MongoDB (if available)
                                            if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                existing_video = self.videos_collection.find_one({"file_id": video_file_id})
                                                if existing_video:
                                                    logger.info(f"Video with file_id {video_file_id} has already been processed, skipping.")
                                                    continue
                                            logger.info("Found video in button click response")
                                            try:
                                                # Try to forward first
                                                access_link = await self.forward_video(new_response)
                                                if access_link:
                                                    logger.info("Successfully forwarded video from button response")
                                                    # Store video in MongoDB (if available)
                                                    if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                        self.videos_collection.insert_one({
                                                            "file_id": video_file_id,
                                                            "access_link": access_link,
                                                            "processed_at": datetime.utcnow()
                                                        })
                                                    access_links.append(access_link)
                                                    videos_found = True
                                                    break  # Stop processing more buttons once video is found
                                                else:
                                                    logger.error("Failed to forward video, trying download and re-upload...")
                                                    # Download and re-upload the video
                                                    access_link = await self.download_and_reupload_video(new_response)
                                                    if access_link:
                                                        # Store video in MongoDB (if available)
                                                        if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                            self.videos_collection.insert_one({
                                                                "file_id": video_file_id,
                                                                "access_link": access_link,
                                                                "processed_at": datetime.utcnow()
                                                            })
                                                        access_links.append(access_link)
                                                        videos_found = True
                                                        break  # Stop processing more buttons once video is found
                                            except Exception as e:
                                                logger.warning(f"Forward failed, trying download and re-upload: {e}")
                                                access_link = await self.download_and_reupload_video(new_response)
                                                if access_link:
                                                    # Store video in MongoDB (if available)
                                                    if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                        self.videos_collection.insert_one({
                                                            "file_id": video_file_id,
                                                            "access_link": access_link,
                                                            "processed_at": datetime.utcnow()
                                                        })
                                                    access_links.append(access_link)
                                                    videos_found = True
                                                    break  # Stop processing more buttons once video is found

                                        await asyncio.sleep(5)  # Increased delay to avoid floodwait
                                    except FloodWaitError as e:
                                        wait_time = e.seconds
                                        logger.warning(f"FloodWaitError in initial button click: Must wait {wait_time} seconds")
                                        await asyncio.sleep(wait_time)
                                    except Exception as e:
                                        logger.error(f"Error clicking button: {e}")
                                    if videos_found:
                                        break  # Break out of button row loop
                                if videos_found:
                                    break  # Break out of button rows loop
                                await asyncio.sleep(3)  # Increased delay to avoid floodwait

                    # Check for message edits and process updated content only once after channels are joined
                    initial_response_text = response.text if hasattr(response, 'text') else ""
                    await asyncio.sleep(3)  # Brief wait for potential edits

                    # Check if the initial response was edited
                    try:
                        current_response = await client.get_messages(bot_username, ids=response.id)
                        if current_response and hasattr(current_response, 'text'):
                            current_text = current_response.text if hasattr(current_response, 'text') else ""
                            if current_text != initial_response_text:
                                logger.info("Initial response was edited! Processing updated content...")
                                response = current_response
                                # Process buttons from edited response
                                if hasattr(response, 'buttons') and response.buttons:
                                    logger.info("Processing buttons from edited response...")
                                    for row_idx, button_row in enumerate(response.buttons):
                                        for btn_idx, button in enumerate(button_row):
                                            if hasattr(button, 'url') and button.url:
                                                if 't.me/' in button.url and ('joinchat' in button.url or '/+' in button.url or '@' in button.url):
                                                    await self.join_channel(button.url)
                                                # Skip URL buttons that contain video-related links, only process target bot links
                                                elif 't.me/' in button.url and 'bot' in button.url and any(bot.strip('@').lower() in button.url.lower() for bot in TARGET_BOT_USERNAMES):
                                                    additional_bot_links.append(button.url)
                                                await asyncio.sleep(5)
                                            elif hasattr(button, 'data'):
                                                try:
                                                    await response.click(button.data)
                                                    new_response = await conv.get_response(timeout=30)
                                                    if hasattr(new_response, 'video') and new_response.video:
                                                        video_file_id = (new_response.video.id, new_response.video.size)
                                                        # Check if video is already processed in MongoDB (if available)
                                                        if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                            existing_video = self.videos_collection.find_one({"file_id": video_file_id})
                                                            if existing_video:
                                                                logger.info(f"Video with file_id {video_file_id} has already been processed, skipping.")
                                                                continue
                                                        access_link = await self.forward_video(new_response)
                                                        if access_link:
                                                            # Store video in MongoDB (if available)
                                                            if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                                self.videos_collection.insert_one({
                                                                    "file_id": video_file_id,
                                                                    "access_link": access_link,
                                                                    "processed_at": datetime.utcnow()
                                                                })
                                                            access_links.append(access_link)
                                                        await asyncio.sleep(5)
                                                except FloodWaitError as e:
                                                    wait_time = e.seconds
                                                    logger.warning(f"FloodWaitError in edited response: Must wait {wait_time} seconds")
                                                    await asyncio.sleep(wait_time)
                                                except Exception as e:
                                                    logger.error(f"Error clicking button in edited response: {e}")
                    except Exception as e:
                        logger.warning(f"Could not check for message edits: {e}")

                    # Check for message edits and process updated content only once after channels are joined
                    initial_response_text = response.text if hasattr(response, 'text') else ""
                    await asyncio.sleep(3)  # Brief wait for potential edits

                    # Check if the initial response was edited
                    try:
                        current_response = await client.get_messages(bot_username, ids=response.id)
                        if current_response and hasattr(current_response, 'text'):
                            current_text = current_response.text if hasattr(current_response, 'text') else ""
                            if current_text != initial_response_text:
                                logger.info("Initial response was edited! Processing updated content...")
                                response = current_response
                                # Process buttons from edited response
                                if hasattr(response, 'buttons') and response.buttons:
                                    logger.info("Processing buttons from edited response...")
                                    for row_idx, button_row in enumerate(response.buttons):
                                        for btn_idx, button in enumerate(button_row):
                                            if hasattr(button, 'url') and button.url:
                                                if 't.me/' in button.url and ('joinchat' in button.url or '/+' in button.url or '@' in button.url):
                                                    await self.join_channel(button.url)
                                                # Skip URL buttons that contain video-related links, only process target bot links
                                                elif 't.me/' in button.url and 'bot' in button.url and any(bot.strip('@').lower() in button.url.lower() for bot in TARGET_BOT_USERNAMES):
                                                    additional_bot_links.append(button.url)
                                                await asyncio.sleep(5)
                                            elif hasattr(button, 'data'):
                                                try:
                                                    await response.click(button.data)
                                                    new_response = await conv.get_response(timeout=30)
                                                    if hasattr(new_response, 'video') and new_response.video:
                                                        video_file_id = (new_response.video.id, new_response.video.size)
                                                        # Check if video is already processed in MongoDB
                                                        existing_video = self.videos_collection.find_one({"file_id": video_file_id})
                                                        if existing_video:
                                                            logger.info(f"Video with file_id {video_file_id} has already been processed, skipping.")
                                                            continue
                                                        access_link = await self.forward_video(new_response)
                                                        if access_link:
                                                            # Store video in MongoDB
                                                            self.videos_collection.insert_one({
                                                                "file_id": video_file_id,
                                                                "access_link": access_link,
                                                                "processed_at": datetime.utcnow()
                                                            })
                                                            access_links.append(access_link)
                                                    await asyncio.sleep(5)
                                                except FloodWaitError as e:
                                                    wait_time = e.seconds
                                                    logger.warning(f"FloodWaitError in edited response: Must wait {wait_time} seconds")
                                                    await asyncio.sleep(wait_time)
                                                except Exception as e:
                                                    logger.error(f"Error clicking button in edited response: {e}")
                    except Exception as e:
                        logger.warning(f"Could not check for message edits: {e}")

                    # Get latest messages for video extraction only once
                    if not videos_found:
                        messages = await client.get_messages(bot_username, limit=20)

                        # Final fetch of all messages for video extraction
                        logger.info("Final fetch: Getting all recent messages from bot for video extraction...")
                        messages = await client.get_messages(bot_username, limit=50)
                        logger.info(f"Retrieved messages from bot (type: {type(messages)})")
                    else:
                        messages = None
                        logger.info("Skipping message fetch since videos were already found in button responses")

                    if messages:
                        video_count = 0
                        try:
                            message_list = list(messages) if hasattr(messages, '__iter__') else [messages]
                            logger.info(f"Processing {len(message_list)} messages")
                            for message in message_list:
                                if hasattr(message, 'video') and message.video:
                                    video_file_id = (message.video.id, message.video.size)
                                    # Check if video is already processed in MongoDB (if available)
                                    if MONGODB_AVAILABLE and self.videos_collection is not None:
                                        existing_video = self.videos_collection.find_one({"file_id": video_file_id})
                                        if existing_video:
                                            logger.info(f"Video with file_id {video_file_id} has already been processed, skipping.")
                                            continue
                                    logger.info(f"Found video in message ID: {getattr(message, 'id', 'unknown')}")
                                    try:
                                        access_link = await self.forward_video(message)
                                        if access_link:
                                            video_count += 1
                                            # Store video in MongoDB (if available)
                                            if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                self.videos_collection.insert_one({
                                                    "file_id": video_file_id,
                                                    "access_link": access_link,
                                                    "processed_at": datetime.utcnow()
                                                })
                                            access_links.append(access_link)
                                            logger.info(f"Successfully forwarded video {video_count}")
                                        else:
                                            logger.warning(f"Forward failed, trying download and re-upload for message {getattr(message, 'id', 'unknown')}")
                                            access_link = await self.download_and_reupload_video(message)
                                            if access_link:
                                                # Store video in MongoDB (if available)
                                                if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                    self.videos_collection.insert_one({
                                                        "file_id": video_file_id,
                                                        "access_link": access_link,
                                                        "processed_at": datetime.utcnow()
                                                    })
                                                access_links.append(access_link)
                                                video_count += 1
                                    except Exception as e:
                                        logger.warning(f"Forward failed, trying download and re-upload: {e}")
                                        access_link = await self.download_and_reupload_video(message)
                                        if access_link:
                                            # Store video in MongoDB (if available)
                                            if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                self.videos_collection.insert_one({
                                                    "file_id": video_file_id,
                                                    "access_link": access_link,
                                                    "processed_at": datetime.utcnow()
                                                })
                                            access_links.append(access_link)
                                            video_count += 1
                                    await asyncio.sleep(3)
                        except (TypeError, AttributeError) as e:
                            logger.warning(f"Could not iterate messages, trying single message approach: {e}")
                            if hasattr(messages, 'video') and messages.video:
                                video_file_id = (messages.video.id, messages.video.size)
                                # Check if video is already processed in MongoDB (if available)
                                if MONGODB_AVAILABLE and self.videos_collection is not None:
                                    existing_video = self.videos_collection.find_one({"file_id": video_file_id})
                                    if existing_video:
                                        logger.info(f"Video with file_id {video_file_id} has already been processed, skipping.")
                                    else:
                                        logger.info(f"Found single video message ID: {getattr(messages, 'id', 'unknown')}")
                                        try:
                                            access_link = await self.forward_video(messages)
                                            if access_link:
                                                logger.info("Successfully forwarded single video")
                                                # Store video in MongoDB (if available)
                                                if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                    self.videos_collection.insert_one({
                                                        "file_id": video_file_id,
                                                        "access_link": access_link,
                                                        "processed_at": datetime.utcnow()
                                                    })
                                                access_links.append(access_link)
                                                video_count = 1
                                            else:
                                                logger.warning("Forward failed, trying download and re-upload for single video")
                                                access_link = await self.download_and_reupload_video(messages)
                                                if access_link:
                                                    # Store video in MongoDB (if available)
                                                    if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                        self.videos_collection.insert_one({
                                                            "file_id": video_file_id,
                                                            "access_link": access_link,
                                                            "processed_at": datetime.utcnow()
                                                        })
                                                    access_links.append(access_link)
                                                    video_count = 1
                                        except Exception as e:
                                            logger.warning(f"Forward failed, trying download and re-upload: {e}")
                                            access_link = await self.download_and_reupload_video(messages)
                                            if access_link:
                                                # Store video in MongoDB (if available)
                                                if MONGODB_AVAILABLE and self.videos_collection is not None:
                                                    self.videos_collection.insert_one({
                                                        "file_id": video_file_id,
                                                        "access_link": access_link,
                                                        "processed_at": datetime.utcnow()
                                                    })
                                                access_links.append(access_link)
                                                video_count = 1
                                else:
                                    logger.info(f"Found single video message ID: {getattr(messages, 'id', 'unknown')}")
                                    try:
                                        access_link = await self.forward_video(messages)
                                        if access_link:
                                            logger.info("Successfully forwarded single video")
                                            access_links.append(access_link)
                                            video_count = 1
                                        else:
                                            logger.warning("Forward failed, trying download and re-upload for single video")
                                            access_link = await self.download_and_reupload_video(messages)
                                            if access_link:
                                                access_links.append(access_link)
                                                video_count = 1
                                    except Exception as e:
                                        logger.warning(f"Forward failed, trying download and re-upload: {e}")
                                        access_link = await self.download_and_reupload_video(messages)
                                        if access_link:
                                            access_links.append(access_link)
                                            video_count = 1
                                await asyncio.sleep(3)

                        logger.info(f"Total videos processed and forwarded: {video_count}")
                        if video_count > 0:
                            # Store processed link in MongoDB (if available)
                            if MONGODB_AVAILABLE and self.links_collection is not None:
                                self.links_collection.insert_one({
                                    "original_link": bot_link,
                                    "access_links": access_links,
                                    "status": "processed",
                                    "processed_at": datetime.utcnow(),
                                    "video_count": video_count
                                })
                                logger.info(f"Stored processed link {bot_link} in database with {video_count} videos")
                    else:
                        logger.warning("No messages retrieved from bot")

            finally:
                # Remove from processing collection (if available)
                if MONGODB_AVAILABLE and self.processing_collection is not None:
                    self.processing_collection.delete_one({"link": bot_link})
                    logger.info(f"Removed {bot_link} from processing collection")

                # Process any additional bot links found in buttons
                for additional_link in additional_bot_links:
                    logger.info(f"Processing additional bot link: {additional_link}")
                    additional_access_links = await self.process_bot_link(additional_link)
                    if additional_access_links:
                        access_links.extend(additional_access_links)

                # Return the list of access links generated
                return access_links if access_links else None

        except (AuthKeyInvalidError, SessionPasswordNeededError,
                PhoneNumberInvalidError, ApiIdInvalidError) as e:
            logger.error(f"Authentication error processing bot link {bot_link}: {str(e)}")
            raise  # Critical error, stop the bot
        except (FloodWaitError, TimeoutError) as e:
            logger.warning(f"Temporary error processing bot link {bot_link}: {str(e)}")
            # Could implement retry logic here
        except (PeerIdInvalidError, ChatWriteForbiddenError,
                UserBannedInChannelError) as e:
            logger.error(f"Access error processing bot link {bot_link}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error processing bot link {bot_link}: {str(e)}")

    async def start(self):
        """Start the userbot"""
        @client.on(events.NewMessage)
        async def handle_new_message(event):
            await self.bot_handlers.handle_new_message(event)

        try:
            logger.info("Starting userbot...")
            await client.start()
            logger.info("Userbot started successfully - monitoring for messages")
            await client.run_until_disconnected()
        except (AuthKeyInvalidError, SessionPasswordNeededError,
                PhoneNumberInvalidError, ApiIdInvalidError) as e:
            logger.error(f"Authentication error starting userbot: {str(e)}")
            logger.error("Please check your API_ID, API_HASH, and ensure your account is not banned")
            raise
        except Exception as e:
            logger.error(f"Critical error in userbot: {str(e)}")
            logger.error("Userbot will now exit")
            raise

async def main():
    userbot = UserBot()
    await userbot.start()

if __name__ == '__main__':
    asyncio.run(main())