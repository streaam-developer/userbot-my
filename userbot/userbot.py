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
        try:
            if bot_link in self.processing_links:
                return
            
            self.processing_links.add(bot_link)
            try:
                async with client.conversation(TARGET_BOT_USERNAME) as conv:
                    await conv.send_message(bot_link)
                    response = await conv.get_response(timeout=30)
                    
                    # Handle channel join requirement
                    if "join" in response.text.lower():
                        channel_links = re.findall(r'https://t\.me/[^\s]+', response.text)
                        for channel_link in channel_links:
                            await self.join_channel(channel_link)
                            await asyncio.sleep(2)  # Avoid flood
                        
                        # Retry sending the link after joining
                        await conv.send_message(bot_link)
                        response = await conv.get_response(timeout=30)
                    
                    # Process all messages in the conversation that contain videos
                    # Get the last few messages from the conversation
                    messages = await client.get_messages(TARGET_BOT_USERNAME, limit=50)  # Get last 50 messages
                    if messages:
                        # Process messages (handle both single message and list)
                        try:
                            for message in messages:
                                if hasattr(message, 'video') and message.video:
                                    await self.forward_video(message)
                                    await asyncio.sleep(1)  # Avoid flood
                        except TypeError:
                            # Single message
                            if hasattr(messages, 'video') and messages.video:
                                await self.forward_video(messages)
                                await asyncio.sleep(1)  # Avoid flood
            
            finally:
                self.processing_links.remove(bot_link)
                
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
                if TARGET_BOT_USERNAME.lower() in event.text.lower():
                    links = re.findall(r'https://t\.me/[^\s]+', event.text)
                    for link in links:
                        await self.process_bot_link(link)
            except Exception as e:
                logger.error(f"Error in message handler: {str(e)}")

        try:
            logger.info("Starting userbot...")
            await client.start()
            logger.info("Userbot started successfully")
            await client.run_until_disconnected()
        except (AuthKeyInvalidError, SessionPasswordNeededError,
                PhoneNumberInvalidError, ApiIdInvalidError) as e:
            logger.error(f"Authentication error starting userbot: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Critical error in userbot: {str(e)}")
            raise

async def main():
    userbot = UserBot()
    await userbot.start()

if __name__ == '__main__':
    asyncio.run(main())