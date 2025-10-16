"""
Bot message handlers and event processing functions
"""
import logging
import re

from config import TARGET_BOT_USERNAMES

logger = logging.getLogger(__name__)

class BotHandlers:
    """Handles bot message events and link processing"""

    def __init__(self, userbot):
        self.userbot = userbot

    async def handle_new_message(self, event):
        """Handle new message events"""
        try:
            logger.info(f"Received new message: {event.text[:100]}...")
            # Check if message contains any target bot username (with or without @) OR any Telegram link
            contains_bot = any(bot.strip('@').lower() in event.text.lower() for bot in TARGET_BOT_USERNAMES)
            links = re.findall(r'https://t\.me/[^\s]+', event.text)

            if contains_bot:
                logger.info(f"Message contains one of target bot usernames: {TARGET_BOT_USERNAMES}")
                logger.info(f"Found {len(links)} Telegram links in message: {links}")
                for link in links:
                    logger.info(f"Processing link: {link}")
                    # Use new workflow: save post temporarily and process for additional channels
                    await self.userbot.process_bot_link_for_additional_channels(link, event)
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
            logger.error(f"Message that caused error: {event.text}")