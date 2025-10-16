import asyncio
import logging
import re

from config import (API_HASH, API_ID, SESSION_NAME, TARGET_BOT_USERNAME,
                    TARGET_BOT_USERNAMES, TARGET_CHANNEL_ID)
from telethon import TelegramClient, events
from telethon.errors import (ApiIdInvalidError, AuthKeyInvalidError,
                             ChannelPrivateError, ChatWriteForbiddenError,
                             FloodWaitError, InviteHashExpiredError,
                             InviteHashInvalidError, PeerIdInvalidError,
                             PhoneNumberInvalidError,
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
            # Extract channel identifier
            if 'joinchat' in channel_link or '/+' in channel_link:
                channel_id = channel_link.split('/')[-1].lstrip('+')
                is_private = True
            else:
                channel_id = channel_link.split('/')[-1]
                is_private = False

            # Check if already joined by trying to get channel info
            try:
                if is_private:
                    # For private channels, we can't easily check without joining
                    await client(ImportChatInviteRequest(channel_id))
                else:
                    # For public channels, check if we're already a member
                    channel = await client.get_entity(channel_id)
                    if hasattr(channel, 'left') and channel.left:
                        await client(JoinChannelRequest(channel_id))
                    else:
                        logger.info(f"Already a member of {channel_link}")
                        return True
            except UserAlreadyParticipantError:
                logger.info(f"Already a member of {channel_link}")
                return True

            logger.info(f"Successfully joined channel: {channel_link}")
            return True
        except (ChannelPrivateError, InviteHashInvalidError, InviteHashExpiredError) as e:
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
            additional_bot_links = []
            try:
                # Extract bot username from the link
                bot_username_match = re.search(r't\.me/([a-zA-Z0-9_]+bot)', bot_link)
                if not bot_username_match:
                    logger.warning(f"Could not extract bot username from link: {bot_link}")
                    # Fallback to target bot username if not found in link
                    bot_username = TARGET_BOT_USERNAME
                else:
                    bot_username = bot_username_match.group(1)

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

                                        if hasattr(new_response, 'video') and new_response.video:
                                            logger.info("Found video in button click response")
                                            success = await self.forward_video(new_response)
                                            if success:
                                                logger.info("Successfully forwarded video from button response")
                                            else:
                                                logger.error("Failed to forward video from button response")

                                        await asyncio.sleep(5)  # Increased delay to avoid floodwait
                                    except FloodWaitError as e:
                                        wait_time = e.seconds
                                        logger.warning(f"FloodWaitError in initial button click: Must wait {wait_time} seconds")
                                        await asyncio.sleep(wait_time)
                                    except Exception as e:
                                        logger.error(f"Error clicking button: {e}")
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
                                                elif 't.me/' in button.url and 'bot' in button.url and any(bot.lower() in button.url.lower() for bot in TARGET_BOT_USERNAMES):
                                                    additional_bot_links.append(button.url)
                                                await asyncio.sleep(5)
                                            elif hasattr(button, 'data'):
                                                try:
                                                    await response.click(button.data)
                                                    new_response = await conv.get_response(timeout=30)
                                                    if hasattr(new_response, 'video') and new_response.video:
                                                        await self.forward_video(new_response)
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
                    messages = await client.get_messages(bot_username, limit=20)

                    # Final fetch of all messages for video extraction
                    logger.info("Final fetch: Getting all recent messages from bot for video extraction...")
                    messages = await client.get_messages(bot_username, limit=50)
                    logger.info(f"Retrieved messages from bot (type: {type(messages)})")

                    if messages:
                        video_count = 0
                        try:
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
                                    await asyncio.sleep(1)
                        except (TypeError, AttributeError) as e:
                            logger.warning(f"Could not iterate messages, trying single message approach: {e}")
                            if hasattr(messages, 'video') and messages.video:
                                logger.info(f"Found single video message ID: {getattr(messages, 'id', 'unknown')}")
                                success = await self.forward_video(messages)
                                if success:
                                    logger.info("Successfully forwarded single video")
                                    video_count = 1
                                else:
                                    logger.error("Failed to forward single video")
                                await asyncio.sleep(1)

                        logger.info(f"Total videos processed and forwarded: {video_count}")
                    else:
                        logger.warning("No messages retrieved from bot")

            finally:
                self.processing_links.remove(bot_link)
                logger.info(f"Removed {bot_link} from processing set. Current processing: {len(self.processing_links)}")

                # Process any additional bot links found in buttons
                for additional_link in additional_bot_links:
                    logger.info(f"Processing additional bot link: {additional_link}")
                    await self.process_bot_link(additional_link)

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
                # Check if message contains any target bot username OR any Telegram link
                contains_bot = any(bot.lower() in event.text.lower() for bot in TARGET_BOT_USERNAMES)
                links = re.findall(r'https://t\.me/[^\s]+', event.text)

                if contains_bot:
                    logger.info(f"Message contains one of target bot usernames: {TARGET_BOT_USERNAMES}")
                    logger.info(f"Found {len(links)} Telegram links in message: {links}")
                    for link in links:
                        logger.info(f"Processing link: {link}")
                        await self.process_bot_link(link)
                elif links:
                    logger.info(f"Message contains {len(links)} Telegram links (no bot username specified)")
                    # Process only links that contain target bot usernames
                    for link in links:
                        # Check if it's a bot link that contains any target bot username (without @)
                        if any(bot.strip('@').lower() in link.lower() for bot in TARGET_BOT_USERNAMES):
                            logger.info(f"Processing target bot link: {link}")
                            await self.process_bot_link(link)
                        else:
                            logger.info(f"Skipping non-target link: {link}")
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