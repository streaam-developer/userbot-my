"""
Bot message handlers and event processing functions
"""
import asyncio
import logging
import re

from config import POST_CHANNEL_ID, TARGET_CHANNEL_ID, TARGET_BOT_USERNAMES

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
                logger.info(f"Message contains target bot links, forwarding to TARGET_CHANNEL first")
                # Forward the entire message to TARGET_CHANNEL first
                target_forwarded = await event.forward_to(TARGET_CHANNEL_ID, drop_author=True)
                logger.info(f"Forwarded message to TARGET_CHANNEL_ID: {TARGET_CHANNEL_ID}")

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

                # Process each target link in parallel and collect access links
                link_replacements = {}
                if target_links:
                    logger.info(f"Processing {len(target_links)} links in parallel")
                    # Process all links concurrently
                    tasks = [self.userbot.process_bot_link(link) for link in target_links]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for link, result in zip(target_links, results):
                        if isinstance(result, Exception):
                            logger.error(f"Error processing link {link}: {str(result)}")
                            link_replacements[link] = link  # Keep original on error
                        elif result:
                            # Handle multiple access links per bot link
                            if isinstance(result, list) and len(result) > 0:
                                # For now, use the first access link, but could be modified to handle multiple
                                link_replacements[link] = result[0]
                                logger.info(f"Processed link {link} -> {result[0]}")
                            else:
                                logger.info(f"No access links generated for {link}, keeping original")
                                link_replacements[link] = link
                        else:
                            logger.info(f"No access links generated for {link}, keeping original")
                            link_replacements[link] = link

                # Replace original links with access links and forward to POST_CHANNEL
                if link_replacements:
                    new_text = event.text
                    for original_link, access_link in link_replacements.items():
                        if access_link != original_link:  # Only replace if we have a different access link
                            new_text = new_text.replace(original_link, access_link)

                    # Forward the modified message to POST_CHANNEL without author
                    post_forwarded = await event.client.send_message(
                        POST_CHANNEL_ID,
                        new_text,
                        file=target_forwarded.media if hasattr(target_forwarded, 'media') else None
                    )
                    logger.info(f"Forwarded modified message to POST_CHANNEL_ID: {POST_CHANNEL_ID}")
                else:
                    logger.info("No link replacements needed, forwarding original to POST_CHANNEL")
                    # Forward original message to POST_CHANNEL without author
                    post_forwarded = await event.forward_to(POST_CHANNEL_ID, drop_author=True)
                    logger.info(f"Forwarded original message to POST_CHANNEL_ID: {POST_CHANNEL_ID}")
            else:
                logger.debug("Message does not contain target bot username or links, ignoring")
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            logger.error(f"Message that caused error: {event.text}")
