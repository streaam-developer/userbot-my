"""
Bot message handlers and event processing functions
"""
import asyncio
import logging
import re

from config import ENABLE_DB_CHECK, ENABLE_DB_UPDATE, TARGET_BOT_USERNAMES, TARGET_CHANNEL_ID
from database import add_processed_url, is_url_processed

logger = logging.getLogger(__name__)

class BotHandlers:
    """Handles bot message events and link processing"""

    def __init__(self, userbot):
        self.userbot = userbot
        self.grouped_messages_cache = {}

    async def handle_new_message(self, event):
        """Handle new message events"""
        if event.grouped_id:
            if event.grouped_id not in self.grouped_messages_cache:
                self.grouped_messages_cache[event.grouped_id] = []
            self.grouped_messages_cache[event.grouped_id].append(event.message)

            # Wait a bit to gather all messages in the group
            await asyncio.sleep(2)

            # Process the group
            await self.process_grouped_messages(event.grouped_id)
        else:
            try:
                if not hasattr(event, 'text') or not event.text:
                    return
                logger.info(f"Received new message: {event.text[:100]}...")
                # Check if message contains any target bot username (with or without @) OR any Telegram link
                contains_bot = any(bot.strip('@').lower() in event.text.lower() for bot in TARGET_BOT_USERNAMES)
                links = re.findall(r'https://t\.me/[^\s]+', event.text)

                if contains_bot:
                    logger.info(f"Message contains one of target bot usernames: {TARGET_BOT_USERNAMES}")
                    logger.info(f"Found {len(links)} Telegram links in message: {links}")
                    for link in links:
                        logger.info(f"Processing link: {link}")
                        await self.userbot.process_bot_link(link)
                elif links:
                    logger.info(f"Message contains {len(links)} Telegram links (no bot username specified)")
                    # Process only links that contain target bot usernames
                    for link in links:
                        # Check if it's a bot link that contains any target bot username (without @)
                        if any(bot.strip('@').lower() in link.lower() for bot in TARGET_BOT_USERNAMES):
                            logger.info(f"Processing target bot link: {link}")
                            await self.userbot.process_bot_link(link)
                        else:
                            logger.info(f"Skipping non-target link: {link}")
                else:
                    logger.debug("Message does not contain target bot username or links, ignoring")
            except Exception as e:
                logger.error(f"Error in message handler: {str(e)}")
                if hasattr(event, 'text'):
                    logger.error(f"Message that caused error: {event.text}")

    async def process_grouped_messages(self, group_id):
        """Process grouped messages, generate new link, and forward them"""
        try:
            messages = self.grouped_messages_cache.pop(group_id, [])
            if not messages:
                return

            caption = None
            for message in messages:
                if message.caption:
                    caption = message.caption
                    break
            
            if not caption:
                logger.debug(f"Group {group_id} has no caption, ignoring.")
                return

            contains_bot = any(bot.strip('@').lower() in caption.lower() for bot in TARGET_BOT_USERNAMES)
            links = re.findall(r'https://t\.me/[^\s]+', caption)

            if not (contains_bot and links):
                logger.debug(f"Group {group_id} caption does not contain target bot or link, ignoring.")
                return

            original_link = links[0]
            logger.info(f"Found link in grouped message caption: {original_link}")

            if ENABLE_DB_CHECK and is_url_processed(original_link):
                logger.info(f"Link {original_link} has already been processed, skipping.")
                return

            new_link = await self.userbot.process_bot_link(original_link)

            if new_link:
                logger.info(f"Successfully generated new link: {new_link}")
                new_caption = caption.replace(original_link, new_link)

                # Forward the grouped photos with the new caption
                await self.userbot.client.send_file(TARGET_CHANNEL_ID, [msg.media for msg in messages], caption=new_caption)
                
                if ENABLE_DB_UPDATE:
                    add_processed_url(original_link)
                    logger.info(f"Added {original_link} to processed URLs database.")
            else:
                logger.warning(f"Failed to generate new link for {original_link}")

        except Exception as e:
            logger.error(f"Error processing group {group_id}: {e}")
