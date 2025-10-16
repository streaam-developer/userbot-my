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
        self.processed_message_ids = set()  # Track processed message IDs to avoid duplicates

    async def handle_new_message(self, event):
        """Handle new message events"""
        try:
            # Check if message contains target bot usernames in text/caption
            message_text = getattr(event, 'text', '') or getattr(event, 'caption', '') or ''
            contains_bot = any(bot.strip('@').lower() in message_text.lower() for bot in TARGET_BOT_USERNAMES)

            if contains_bot:
                logger.info("Message contains target bot username, processing for reposting")
                await self.process_channel_post(event)
            else:
                # Original logic for messages containing bot usernames or links
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
            logger.error(f"Message that caused error: {event.text}")

    async def process_channel_post(self, event):
        """Process channel posts that contain target bot usernames"""
        try:
            message_id = event.id
            if message_id in self.processed_message_ids:
                logger.info(f"Message ID {message_id} already processed, skipping")
                return

            logger.info(f"Processing channel post ID: {message_id}")

            # Save post details
            post_details = {
                'message_id': message_id,
                'text': getattr(event, 'text', ''),
                'caption': getattr(event, 'caption', ''),
                'media': event.media if hasattr(event, 'media') else None,
                'buttons': event.buttons if hasattr(event, 'buttons') else None,
                'sender_username': getattr(event.sender, 'username', None),
                'date': event.date,
                'original_link': None  # Will be set if video processing succeeds
            }

            # Extract bot links from the message text/caption
            message_text = post_details['text'] or post_details['caption'] or ''
            bot_links = re.findall(r'https://t\.me/[^\s\n]+', message_text)

            if bot_links:
                logger.info(f"Found {len(bot_links)} bot links in post: {bot_links}")
                # Process the first bot link (assuming it's the target)
                target_link = bot_links[0]
                logger.info(f"Processing target link: {target_link}")

                try:
                    # Process the bot link to get video and generate access link
                    await self.userbot.process_bot_link(target_link)

                    # After processing, we need to wait for the video to be uploaded and get the access link
                    # For now, we'll simulate getting the access link from the last processed video
                    # In a real implementation, you'd need to track which link generated which video
                    access_link = await self.get_latest_access_link()
                    if access_link:
                        post_details['original_link'] = access_link
                        # Replace original link in caption/text with access link
                        modified_text = self.replace_link_in_text(message_text, access_link)
                        post_details['modified_text'] = modified_text

                        # Repost to POST_CHANNEL_ID with original media and modified text
                        try:
                            await self.repost_channel_content(post_details)
                        except Exception as e:
                            logger.error(f"Failed to repost message ID {message_id} to POST_CHANNEL_ID: {str(e)}")
                            # Don't mark as processed if reposting failed
                            return

                        # Mark as processed
                        self.processed_message_ids.add(message_id)
                        logger.info(f"Successfully processed and reposted channel post ID: {message_id}")
                    else:
                        logger.error(f"Failed to get access link for message ID: {message_id}")
                        # Don't mark as processed, allow retry on next message
                except Exception as e:
                    logger.error(f"Error processing bot link for message ID {message_id}: {str(e)}")
                    # Don't mark as processed, allow retry
            else:
                logger.info(f"Message ID {message_id} has no bot links, skipping")

        except Exception as e:
            logger.error(f"Error processing channel post: {str(e)}")
            logger.error(f"Message details: ID={event.id}, Text={getattr(event, 'text', '')[:200]}...")

    async def get_latest_access_link(self):
        """Get the latest generated access link"""
        try:
            # Get the latest access link from the userbot's mapping
            return self.userbot.link_to_access_map.get('latest')
        except Exception as e:
            logger.error(f"Error getting latest access link: {str(e)}")
            return None

    def replace_link_in_text(self, text, new_link):
        """Replace Telegram links in text with the new access link"""
        try:
            # Find all Telegram links in the text
            telegram_links = re.findall(r'https://t\.me/[^\s\n]+', text)
            if telegram_links:
                # Replace the first Telegram link with the new access link
                # Assuming the first link is the one to replace
                old_link = telegram_links[0]
                modified_text = text.replace(old_link, new_link)
                logger.info(f"Replaced link in text: {old_link} -> {new_link}")
                return modified_text
            else:
                # If no links found, append the access link
                modified_text = text + f"\n\nAccess Link: {new_link}"
                logger.info("No links found in text, appended access link")
                return modified_text
        except Exception as e:
            logger.error(f"Error replacing link in text: {str(e)}")
            return text

    async def repost_channel_content(self, post_details):
        """Repost channel content with modified text to POST_CHANNEL_ID"""
        try:
            # Prepare the message content
            text = post_details.get('modified_text', post_details.get('text', ''))
            media = post_details.get('media')
            buttons = post_details.get('buttons')

            # Create message with same format
            message_kwargs = {
                'message': text,
            }

            # Add media if present (keep original media - photos, videos, etc.)
            if media:
                message_kwargs['file'] = media

            # Add buttons if present (keep original buttons)
            if buttons:
                message_kwargs['buttons'] = buttons

            # Send to POST_CHANNEL_ID
            await self.userbot.client.send_message(POST_CHANNEL_ID, **message_kwargs)
            logger.info(f"Successfully reposted channel content to POST_CHANNEL_ID: {POST_CHANNEL_ID}")

        except Exception as e:
            logger.error(f"Error reposting channel content: {str(e)}")
            logger.error(f"Post details: {post_details}")
            # Re-raise to allow caller to handle posting restrictions
            raise

    async def repost_modified_content(self, post_details):
        """Repost the modified content to POST_CHANNEL_ID"""
        try:
            # Prepare the message content
            text = post_details.get('modified_text', post_details.get('text', ''))
            media = post_details.get('media')
            buttons = post_details.get('buttons')

            # Create message with same format
            message_kwargs = {
                'message': text,
            }

            # Add media if present
            if media:
                message_kwargs['file'] = media

            # Add buttons if present (keep original buttons)
            if buttons:
                message_kwargs['buttons'] = buttons

            # Send to POST_CHANNEL_ID
            await self.userbot.client.send_message(POST_CHANNEL_ID, **message_kwargs)
            logger.info(f"Successfully reposted modified content to POST_CHANNEL_ID: {POST_CHANNEL_ID}")

        except Exception as e:
            logger.error(f"Error reposting modified content: {str(e)}")
            logger.error(f"Post details: {post_details}")
            # Re-raise to allow caller to handle posting restrictions
            raise