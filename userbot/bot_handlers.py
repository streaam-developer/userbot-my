"""
Bot message handlers and event processing functions
"""
import logging
import re

from config import POST_CHANNEL_ID, TARGET_BOT_USERNAMES

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

            if contains_bot or (links and any(any(bot.strip('@').lower() in link.lower() for bot in TARGET_BOT_USERNAMES) for link in links)):
                logger.info(f"Message contains target bot links, forwarding to POST_CHANNEL")
                # Forward the entire message to POST_CHANNEL without author
                forwarded_message = await event.forward_to(POST_CHANNEL_ID, drop_author=True)
                logger.info(f"Forwarded message to POST_CHANNEL_ID: {POST_CHANNEL_ID}")

                # Extract and process target bot links
                target_links = []
                if contains_bot:
                    logger.info(f"Message contains one of target bot usernames: {TARGET_BOT_USERNAMES}")
                    logger.info(f"Found {len(links)} Telegram links in message: {links}")
                    target_links = links
                elif links:
                    logger.info(f"Message contains {len(links)} Telegram links (no bot username specified)")
                    # Process only links that contain target bot usernames
                    for link in links:
                        # Check if it's a bot link that contains any target bot username (without @)
                        if any(bot.strip('@').lower() in link.lower() for bot in TARGET_BOT_USERNAMES):
                            target_links.append(link)
                        else:
                            logger.info(f"Skipping non-target link: {link}")

                # Process multiple target links concurrently
                link_replacements = {}
                if target_links:
                    logger.info(f"Processing {len(target_links)} links concurrently")
                    # Create tasks for concurrent processing
                    tasks = [self.userbot.process_bot_link(link) for link in target_links]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Process results
                    for link, result in zip(target_links, results):
                        if isinstance(result, Exception):
                            logger.error(f"Error processing link {link}: {result}")
                            link_replacements[link] = link  # Keep original link on error
                        elif result:
                            # Assuming one access link per bot link for simplicity
                            link_replacements[link] = result[0] if result else link
                        else:
                            link_replacements[link] = link  # Keep original if no result

                # Replace original links with access links in the forwarded message
                if link_replacements:
                    new_text = event.text
                    for original_link, access_link in link_replacements.items():
                        new_text = new_text.replace(original_link, access_link)
                    await forwarded_message.edit(new_text)
                    logger.info("Replaced original links with access links in forwarded message")
            else:
                logger.debug("Message does not contain target bot username or links, ignoring")
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            logger.error(f"Message that caused error: {event.text}")
