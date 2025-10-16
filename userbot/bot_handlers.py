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
            # Check if message is from a target bot username
            sender_username = getattr(event.sender, 'username', None)
            if sender_username and any(bot.strip('@').lower() == sender_username.lower() for bot in TARGET_BOT_USERNAMES):
                logger.info(f"Message from target bot: @{sender_username}")
                await self.process_target_bot_message(event)
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

    async def process_target_bot_message(self, event):
        """Process messages from target bot usernames"""
        try:
            message_id = event.id
            if message_id in self.processed_message_ids:
                logger.info(f"Message ID {message_id} already processed, skipping")
                return

            logger.info(f"Processing target bot message ID: {message_id}")

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

            # Check if message has video
            if hasattr(event, 'video') and event.video:
                logger.info("Message contains video, processing for access link generation")
                try:
                    # Process video and get access link
                    access_link = await self.userbot.process_video_for_link(event)
                    if access_link:
                        post_details['original_link'] = access_link
                        # Replace original link in caption/text with access link
                        modified_text = self.replace_link_in_text(post_details['text'] or post_details['caption'] or '', access_link)
                        post_details['modified_text'] = modified_text

                        # Repost to POST_CHANNEL_ID
                        try:
                            await self.repost_modified_content(post_details)
                        except Exception as e:
                            logger.error(f"Failed to repost message ID {message_id} to POST_CHANNEL_ID: {str(e)}")
                            # Don't mark as processed if reposting failed
                            return

                        # Mark as processed
                        self.processed_message_ids.add(message_id)
                        logger.info(f"Successfully processed and reposted message ID: {message_id}")
                    else:
                        logger.error(f"Failed to generate access link for message ID: {message_id}")
                        # Don't mark as processed, allow retry on next message
                except Exception as e:
                    logger.error(f"Error processing video for message ID {message_id}: {str(e)}")
                    # Don't mark as processed, allow retry
            else:
                logger.info(f"Message ID {message_id} has no video, skipping")

        except Exception as e:
            logger.error(f"Error processing target bot message: {str(e)}")
            logger.error(f"Message details: ID={event.id}, Text={getattr(event, 'text', '')[:200]}...")

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