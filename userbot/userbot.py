import asyncio
import logging
import re

from config import (API_HASH, API_ID, SESSION_NAME, TARGET_BOT_USERNAME,
                    TARGET_CHANNEL_ID)
from telethon import TelegramClient, events
from telethon.errors import (ApiIdInvalidError, AuthKeyInvalidError,
                             ChannelPrivateError, ChatWriteForbiddenError,
                             FloodWaitError, InviteHashInvalidError,
                             PeerIdInvalidError, PhoneNumberInvalidError,
                             SessionPasswordNeededError, TimeoutError,
                             UserAlreadyParticipantError,
                             UserBannedInChannelError)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

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
        self.processing_links = set()
        self.retries = {}
        self.max_retries = 3
        self.retry_delay = 60  # seconds

    async def join_channel(self, channel_link):
        """Join a channel with error handling and retry mechanism"""
        try:
            if 'joinchat' in channel_link:
                invite_hash = channel_link.split('/')[-1]
                await client(ImportChatInviteRequest(invite_hash))
            else:
                channel_username = channel_link.split('/')[-1]
                await client(JoinChannelRequest(channel_username))
            logger.info(f"Successfully joined channel: {channel_link}")
            return True
        except UserAlreadyParticipantError:
            logger.info(f"Already a member of {channel_link}")
            return True
        except (ChannelPrivateError, InviteHashInvalidError) as e:
            logger.error(f"Cannot join channel {channel_link}: {str(e)}")
            return False
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"FloodWaitError: Must wait {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return await self.join_channel(channel_link)
        except Exception as e:
            logger.error(f"Unexpected error joining channel {channel_link}: {str(e)}")
            return False

    async def forward_video(self, message, retry_count=0):
        """Forward video to target channel with error handling"""
        try:
            await message.forward_to(TARGET_CHANNEL_ID)
            logger.info(f"Successfully forwarded video from message ID: {message.id}")
            return True
        except FloodWaitError as e:
            if retry_count < self.max_retries:
                wait_time = e.seconds
                logger.warning(f"FloodWaitError: Waiting {wait_time} seconds before retry")
                await asyncio.sleep(wait_time)
                return await self.forward_video(message, retry_count + 1)
            else:
                logger.error("Max retries reached for forwarding video")
                return False
        except Exception as e:
            logger.error(f"Error forwarding video: {str(e)}")
            return False

    async def process_bot_link(self, bot_link):
        """Process bot link and extract videos"""
        logger.info(f"Starting to process bot link: {bot_link}")
        try:
            if bot_link in self.processing_links:
                logger.info(f"Link {bot_link} is already being processed, skipping")
                return

            self.processing_links.add(bot_link)
            logger.info(f"Added {bot_link} to processing set. Current processing: {len(self.processing_links)}")
            try:
                # Extract the start parameter or any bot command from the link
                if 'start=' in bot_link:
                    # This is a bot start link, extract the parameter
                    start_param = bot_link.split('start=')[-1]
                    bot_command = f"/start {start_param}"
                    logger.info(f"Extracted start parameter: {start_param}, using command: {bot_command}")
                else:
                    # Use the link as is
                    bot_command = bot_link
                    logger.info(f"Using link as command: {bot_command}")

                logger.info(f"Starting conversation with {TARGET_BOT_USERNAME}")
                async with client.conversation(TARGET_BOT_USERNAME) as conv:
                    logger.info(f"Sending command to bot: {bot_command}")
                    await conv.send_message(bot_command)
                    logger.info("Waiting for bot response...")
                    response = await conv.get_response(timeout=30)
                    logger.info(f"Received response from bot: {response.text[:200]}...")

                    # Handle channel join requirement
                    if "join" in response.text.lower() or "channel" in response.text.lower():
                        logger.info("Bot requires channel join, extracting channel links...")
                        # More comprehensive regex to find various Telegram link formats
                        channel_links = re.findall(r'https://t\.me/[^\s\n]+', response.text)
                        # Also try to find @username format
                        username_links = re.findall(r'@([a-zA-Z0-9_]+)', response.text)
                        # Convert usernames to links
                        for username in username_links:
                            if username not in ['join', 'channel', 'the', 'to', 'and', 'or']:  # Filter common words
                                channel_links.append(f"https://t.me/{username}")

                        logger.info(f"Found {len(channel_links)} channel links to join: {channel_links}")
                        joined_any = False
                        for channel_link in channel_links:
                            # Skip if it's the bot itself
                            if TARGET_BOT_USERNAME.lower() in channel_link.lower():
                                logger.info(f"Skipping bot link: {channel_link}")
                                continue
                            logger.info(f"Attempting to join channel: {channel_link}")
                            success = await self.join_channel(channel_link)
                            if success:
                                logger.info(f"Successfully joined channel: {channel_link}")
                                joined_any = True
                            else:
                                logger.error(f"Failed to join channel: {channel_link}")
                            await asyncio.sleep(2)  # Avoid flood

                        # After joining, get the content by sending the command again
                        if joined_any:
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
                                    # Check if it's a channel link that needs joining
                                    if 't.me/' in button.url and ('joinchat' in button.url or '/+' in button.url or '@' in button.url):
                                        logger.info(f"Button contains channel link, attempting to join: {button.url}")
                                        success = await self.join_channel(button.url)
                                        if success:
                                            logger.info(f"Successfully joined channel from button: {button.url}")
                                        else:
                                            logger.error(f"Failed to join channel from button: {button.url}")
                                    else:
                                        # Process as a potential bot link
                                        logger.info(f"Processing button URL as bot link: {button.url}")
                                        await self.process_bot_link(button.url)
                                    await asyncio.sleep(2)  # Wait between button clicks
                                elif hasattr(button, 'data'):
                                    logger.info(f"Clicking inline button with data: {button.data}")
                                    try:
                                        # Click the button to get more content
                                        await response.click(button.data)
                                        # Wait for and process the new response
                                        new_response = await conv.get_response(timeout=30)
                                        logger.info(f"Received response after button click: {new_response.text[:200]}...")

                                        # Process videos from the new response
                                        if hasattr(new_response, 'video') and new_response.video:
                                            logger.info("Found video in button click response")
                                            success = await self.forward_video(new_response)
                                            if success:
                                                logger.info("Successfully forwarded video from button response")
                                            else:
                                                logger.error("Failed to forward video from button response")

                                        await asyncio.sleep(2)  # Wait between responses
                                    except Exception as e:
                                        logger.error(f"Error clicking button: {e}")
                                await asyncio.sleep(1)  # Avoid flood

                    # Process all messages in the conversation that contain videos
                    logger.info("Fetching recent messages from bot for video extraction...")
                    # Get the last few messages from the conversation
                    messages = await client.get_messages(TARGET_BOT_USERNAME, limit=50)  # Get last 50 messages
                    logger.info(f"Retrieved messages from bot (type: {type(messages)})")

                    if messages:
                        video_count = 0
                        # Process messages (handle both single message and list)
                        try:
                            # Try to iterate through messages
                            message_list = list(messages) if hasattr(messages, '__iter__') else [messages]
                            logger.info(f"Processing {len(message_list)} messages")
                            for message in message_list:
                                if hasattr(message, 'video') and message.video:
                                    logger.info(f"Found video in message ID: {getattr(message, 'id', 'unknown')}")
                                    success = await self.forward_video(message)
                                    if success:
                                        video_count += 1
                                        logger.info(f"Successfully forwarded video {video_count}")
                                    else:
                                        logger.error(f"Failed to forward video from message ID: {getattr(message, 'id', 'unknown')}")
                                    await asyncio.sleep(1)  # Avoid flood
                        except (TypeError, AttributeError) as e:
                            logger.warning(f"Could not iterate messages, trying single message approach: {e}")
                            # Single message fallback
                            if hasattr(messages, 'video') and messages.video:
                                logger.info(f"Found single video message ID: {getattr(messages, 'id', 'unknown')}")
                                success = await self.forward_video(messages)
                                if success:
                                    logger.info("Successfully forwarded single video")
                                    video_count = 1
                                else:
                                    logger.error("Failed to forward single video")
                                await asyncio.sleep(1)  # Avoid flood

                        logger.info(f"Total videos processed and forwarded: {video_count}")
                    else:
                        logger.warning("No messages retrieved from bot")

            finally:
                self.processing_links.remove(bot_link)
                logger.info(f"Removed {bot_link} from processing set. Current processing: {len(self.processing_links)}")

                
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
            try:
                logger.info(f"Received new message: {event.text[:100]}...")
                # Check if message contains target bot username OR any Telegram link
                contains_bot = TARGET_BOT_USERNAME.lower() in event.text.lower()
                links = re.findall(r'https://t\.me/[^\s]+', event.text)

                if contains_bot:
                    logger.info(f"Message contains target bot username: {TARGET_BOT_USERNAME}")
                    logger.info(f"Found {len(links)} Telegram links in message: {links}")
                    for link in links:
                        logger.info(f"Processing link: {link}")
                        await self.process_bot_link(link)
                elif links:
                    logger.info(f"Message contains {len(links)} Telegram links (no bot username specified)")
                    # Process all Telegram links found, regardless of bot username
                    for link in links:
                        # Check if it's a bot link (contains bot username in URL or is a direct bot link)
                        if TARGET_BOT_USERNAME.lower() in link.lower() or 'bot' in link.lower():
                            logger.info(f"Processing bot link: {link}")
                            await self.process_bot_link(link)
                        else:
                            logger.info(f"Skipping non-bot link: {link}")
                else:
                    logger.debug("Message does not contain target bot username or links, ignoring")
            except Exception as e:
                logger.error(f"Error in message handler: {str(e)}")
                logger.error(f"Message that caused error: {event.text}")

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